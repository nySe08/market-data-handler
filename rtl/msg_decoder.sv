// Milestone 3: market-data message decoder
//
// Input : payload byte stream from eth_ip_udp_parser (1 byte per cycle).
//         A payload holds one or more 16-byte Level Update messages.
// Output: the decoded fields of each message, with a 1-cycle msg_valid pulse.
//
// Message layout (big-endian, see docs/SPEC.md):
//   byte 0      msg_type   'U' = 0x55
//   byte 1      side       'B' = 0x42 (bid) / 'S' = 0x53 (ask)
//   bytes 2-3   instrument
//   bytes 4-7   price
//   bytes 8-11  qty
//   bytes 12-15 seq
module msg_decoder (
    input  logic        clk,
    input  logic        rst,          // synchronous, active-high

    // input: payload bytes
    input  logic        s_tvalid,
    input  logic [7:0]  s_tdata,
    input  logic        s_tlast,      // last byte of the payload (end of packet)

    // output: one decoded message
    output logic        msg_valid,    // 1-cycle pulse per decoded message
    output logic        msg_is_bid,   // 1 = bid, 0 = ask
    output logic [15:0] msg_instrument,
    output logic [31:0] msg_price,
    output logic [31:0] msg_qty,
    output logic [31:0] msg_seq
);

    logic [3:0]   pos;     // byte position inside the current message (0..15)
    logic [119:0] shreg;   // the first 15 bytes of the current message

    // ------------------------------------------------------------------
    // Combinational: the full 16-byte message, available in the SAME cycle
    // the last byte arrives (15 stored bytes + the incoming byte).
    // Byte 0 ends up in the top bits, byte 15 in the bottom bits.
    // ------------------------------------------------------------------
    logic [127:0] msg;
    assign msg = {shreg, s_tdata};

    // field slices of msg
    logic [7:0] f_type, f_side;
    assign f_type = msg[127:120];
    assign f_side = msg[119:112];

    // is this a message we understand?
    logic msg_ok;
    assign msg_ok = (f_type == 8'h55) && (f_side == 8'h42 || f_side == 8'h53);

    // ------------------------------------------------------------------
    // Sequential
    // ------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            pos            <= '0;
            shreg          <= '0;
            msg_valid      <= 1'b0;
            msg_is_bid     <= 1'b0;
            msg_instrument <= '0;
            msg_price      <= '0;
            msg_qty        <= '0;
            msg_seq        <= '0;
        end else begin
            msg_valid <= 1'b0;                     // default: no message

            if (s_tvalid) begin
                // shift the new byte in (oldest byte falls out the top)
                shreg <= {shreg[111:0], s_tdata};

                // 16th byte of a message -> decode and output it
                if (pos == 4'd15 && msg_ok) begin
                    msg_valid      <= 1'b1;
                    msg_is_bid     <= (f_side == 8'h42);
                    msg_instrument <= msg[111:96];
                    msg_price      <= msg[95:64];
                    msg_qty        <= msg[63:32];
                    msg_seq        <= msg[31:0];
                end

                // next byte position:
                //  - end of packet -> next byte starts a new message
                //  - otherwise count 0..15; 15 + 1 wraps to 0 by itself (4 bits)
                if (s_tlast)
                    pos <= '0;
                else
                    pos <= pos + 1'b1;
            end
        end
    end

endmodule
