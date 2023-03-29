"""Simple file to stand up a serial server.

This is meant for hosting a stm32 flash binary.
"""
import serial
import sys


class TftpServer:
    OPCODE_READ = b"1"
    OPCODE_WRITE = b"10"
    OPCODE_DATA = b"11"
    OPCODE_ACK = b"100"
    OPCODE_ERR = b"101"

    STATE_WAITING = 0
    STATE_READING = 1
    STATE_WRITING = 2
    STATE_ERR = 3

    tftp_block_size = 512
    write_no_ack_retry = 3
    err_str = ""

    def get_opcode(self, input_string):
        """Helper function to get the opcode from an input string.

        @param self         The current object.
        @param input_string The input string to grab the opcode from.
        @return             The opcode from the string.
        """

        return input_string[0:2]

    def wait_for_valid_ack(self, server, num_retries, block_counter):
        for _ in range(num_retries):
            acq = server.read(4)
            self.get_opcode(acq)
            block_id = acq[2:]

            if block_id == block_counter:
                return True
            else:
                print(
                    f"Expecting block acq on block id {block_counter}."
                    f"Instead got {block_id}"
                )

        # If we got here, then we failed to acq the block.
        return False

    def run_sm(self, server, file):
        current_state = self.STATE_WAITING

        while(1):
            # The waiting state where we should go to between read requests
            # and after handling errors.
            if current_state == self.STATE_WAITING:
                # Set the timeout to None to wait indefinitaly for the next
                # RRQ.
                server.timeout = None

                # Wait on the opcode to dictate what we should do here.
                server_request = server.read()
                opcode = self.get_opcode(server_request)

                # This is a read request. As the server, we should transfer to
                # the writing state to fulfill the client's read request.
                if opcode == self.OPCODE_READ:
                    print(f"Recieved read request for {file}!")
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
                    print(
                        f"Got an unexpected opcode of {opcode} in the waiting"
                        " state. Throwing err :("
                    )
                    self.err_str = (
                        f"Requested opcode {opcode} is not a valid opcode in"
                        " the waiting state."
                    )
                    current_state = self.STATE_ERR

            # The writing state. Send the desired file to out the serial
            # server.
            elif current_state == self.STATE_WRITING:
                # Reset the block counter and set the timeout to 2s, this is
                # how long we will wait for an acq for each data block.
                server.timeout = 2
                block_counter = 0

                # If the last read size of the file is less than the tftp
                # block size, we are at the end of the file and now can move
                # on.
                last_read_block_size = self.tftp_block_size
                while last_read_block_size == self.tftp_block_size:
                    # Frame our message with the correct opcode and block
                    # counter.
                    message = str(self.OPCODE_DATA)
                    message += str(block_counter)

                    # Read the request amount of the file and add it the
                    # message to be sent.
                    read_block = file.read(self.tftp_block_size)
                    message += read_block
                    last_read_block_size = len(read_block)

                    # Write our message.
                    server.write(message)

                    if self.wait_for_valid_ack(
                        server, self.write_no_ack_retry, block_counter
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
    tftp_server = TftpServer()
    try:
        server = serial.Serial(usb_device_name, serial_baud_rate)

        # Close the server before opening to be sure that the call to "open"
        # doesn't fail.
        server.close()
        server.open()

        print("Starting TFTP server!")
        print(f"Opening file {args[0][0]}")

        f = open(args[0][0], "r")


        if f.closed:
            print("file failed to open")
        else:
            tftp_server.run_sm(server, f)

    except:
        server.close()


if __name__ == "__main__":
    main(sys.argv[1:])
