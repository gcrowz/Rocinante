"""Simple file to stand up a serial server.

This is meant for hosting a stm32 flash binary.
"""
import serial
import sys


class TftpServer:
    OPCODE_READ = b"\x00\x01"
    OPCODE_WRITE = b"\x00\x02"
    OPCODE_DATA = b"\x00\x03"
    OPCODE_ACK = b"\x00\x04"
    OPCODE_ERR = b"\x00\x05"

    STATE_WAITING = 0
    STATE_READING = 1
    STATE_WRITING = 2
    STATE_ERR = 3

    tftp_block_size = 512
    write_no_ack_retry = 3
    err_str = ""
    file = None


    def __init__(self, file):
        self.file = file


    def __del__(self):
        self.file.close()


    def get_opcode(self, input_string):
        """Helper function to get the opcode from an input string.

        @param self         The current object.
        @param input_string The input string to grab the opcode from.
        @return             The opcode from the string.
        """

        return input_string[0:2]


    def parse_ack(self, given, expected_block):
        valid_ack = given[0] == self.OPCODE_ACK
        correct_block = given[1] == int(expected_block).to_bytes(2, 'big')

        if valid_ack and correct_block:
            return True
        else:
            print(
                f"Expected opcode of {self.OPCODE_ACK}. Got opcode of {given[0]}"
            )
            print(
                f"Expected block counter of {expected_block}. Got block counter of {given[1]}"
            )


    def wait_for_valid_ack(self, server, num_retries, block_counter, first_attempt):
        attempt = first_attempt
        for _ in range(num_retries):
            if self.parse_ack((self.get_opcode(attempt), attempt[2:4]), block_counter):
                print(f"Valid acq on block {block_counter}")
                return True

            attempt = server.read(4)

        # If we got here, then we failed to acq the block.
        return False

    def run_sm(self, server):
        current_state = self.STATE_WAITING

        while(1):
            # The waiting state where we should go to between read requests
            # and after handling errors.
            if current_state == self.STATE_WAITING:
                # Set the timeout to None to wait indefinitaly for the next
                # RRQ.
                server.timeout = None

                # Wait on the opcode to dictate what we should do here.
                server_request = server.read(2)
                opcode = self.get_opcode(server_request)

                # This is a read request. As the server, we should transfer to
                # the writing state to fulfill the client's read request.
                if opcode == self.OPCODE_READ:
                    print(f"Recieved read request for {self.file}!")
                    current_state = self.STATE_WRITING

                # This is a write request. As the server, we should never
                # expect this. We should throw an unimplemented error as this
                # was most likely a client side issue.
                elif opcode == self.OPCODE_WRITE:
                    print(
                        f"Got an unexpected opcode of {opcode} in the waiting"
                        " state. Throwing err :("
                    )
                    self.err_str = f"Requested opcode {opcode} is" \
                                   f"unimplemented"
                    current_state = self.STATE_ERR

                # Throw and error if have an expect opcode for this state.
                else:
                    server.timeout = 1
                    server_request += server.read_until('\n')
                    server.timeout = None

                    print(f"{server_request}")

            # The writing state. Send the desired file to out the serial
            # server.
            elif current_state == self.STATE_WRITING:
                # Reset the block counter and set the timeout to 2s, this is
                # how long we will wait for an acq for each data block.
                server.timeout = 2
                block_counter = 0
                print("Starting write")

                # If the last read size of the file is less than the tftp
                # block size, we are at the end of the file and now can move
                # on.
                last_read_block_size = self.tftp_block_size
                while last_read_block_size == self.tftp_block_size:
                    # Frame our message with the correct opcode and block
                    # counter.
                    print("sending message")
                    message = self.OPCODE_DATA
                    message += block_counter.to_bytes(2, 'big')

                    read_block = self.file.read(self.tftp_block_size)
                    last_read_block_size = len(read_block)

                    message += last_read_block_size.to_bytes(2, 'big')
                    message += read_block

                    # Print out the message we want to send in hex
                    print(''.join('{:02x} '.format(x) for x in message))

                    # Write our message.
                    server.write(message)

                    acq = server.read(4)
                    # rply = server.read(last_read_block_size)

                    # print("recived this from the client")
                    # print(''.join('{:02x} '.format(x) for x in rply))

                    if self.wait_for_valid_ack(
                        server, self.write_no_ack_retry, block_counter, acq
                    ):
                        block_counter += 1
                    else:
                        current_state = self.STATE_ERR
                        self.err_str = (
                            f"Never received acq for block {block_counter}"
                        )

                if current_state == self.STATE_WRITING:
                    current_state = self.STATE_WAITING

            elif current_state == self.STATE_ERR:
                message = str(self.OPCODE_ERR)
                message += str(0) + str(0)
                message += self.err_str
                server.write(message)
                self.err_str = ""

                current_state = self.STATE_WAITING

            else:
                print(f"Hit unimplemented state {current_state}")
                self.err_str = f"Hit unimplemented state {current_state}"

                current_state = self.STATE_ERR


def main(*args):
    usb_device_name = "/dev/tty.usbmodem2103"
    serial_baud_rate = 115200
    try:
        server = serial.Serial(usb_device_name, serial_baud_rate)

        # Close the server before opening to be sure that the call to "open"
        # doesn't fail.
        server.close()
        server.open()

        print("Starting TFTP server!")
        print(f"Opening file {args[0][0]}")

        f = open(args[0][0], "rb")
        tftp_server = TftpServer(f)

        if f.closed:
            print("file failed to open")
        else:
            tftp_server.run_sm(server)

    except:
        server.close()


if __name__ == "__main__":
    main(sys.argv[1:])
