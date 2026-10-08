// Milestone 2: Ethernet / IPv4 / UDP header parser
//
// Takes a raw frame (1 byte per cycle) and outputs ONLY the UDP payload
// bytes of frames that pass all header checks. See docs/SPEC.md.
//
// Key idea: every field we must check sits in bytes 12..39, i.e. BEFORE the
// payload starts at byte 42. So by the time the first payload byte arrives we
// already know whether the frame is valid -> no buffering needed, we can
// stream the payload straight through ("cut-through"), which is what keeps
// latency low.
module eth_ip_udp_parser #(
    parameter logic [15:0] UDP_PORT = 16'd26400   // 0x6720
) (
    input  logic       clk,
    input  logic       rst,      // synchronous, active-high

    // input: raw frame bytes (FCS already stripped)
    input  logic       s_tvalid,
    input  logic [7:0] s_tdata,
    input  logic       s_tlast,

    // output: payload bytes only
    output logic       m_tvalid,
    output logic [7:0] m_tdata,
    output logic       m_tlast    // high on the last payload byte
);

    localparam int PAYLOAD_START = 42;  // 14 eth + 20 ip + 8 udp

    logic [10:0] idx;       // byte index inside the current frame (frames <= 2047 B)
    logic        ok;        // 1 = every check so far has passed
    logic [15:0] udp_len;   // UDP length field (header + payload)

    // ------------------------------------------------------------------
    // Combinational: does the CURRENT byte match what we expect here?
    // Bytes we don't care about are always "ok".
    // ------------------------------------------------------------------
    logic byte_ok;
    always_comb begin
        case (idx)
            11'd12:  byte_ok = (s_tdata == 8'h08);            // EtherType hi
            11'd13:  byte_ok = (s_tdata == 8'h00);            // EtherType lo
            11'd14:  byte_ok = (s_tdata == 8'h45);            // IPv4, no options
            11'd23:  byte_ok = (s_tdata == 8'd17);            // protocol = UDP
            11'd36:  byte_ok = (s_tdata == UDP_PORT[15:8]);   // dst port hi
            11'd37:  byte_ok = (s_tdata == UDP_PORT[7:0]);    // dst port lo
            default: byte_ok = 1'b1;
        endcase
    end

    // ------------------------------------------------------------------
    // Combinational: is the current byte inside the payload window?
    // Last payload byte index = 42 + (udp_len - 8) - 1 = udp_len + 33
    // ------------------------------------------------------------------
    logic [15:0] payload_end;
    logic        in_payload;
    assign payload_end = udp_len + 16'd33;
    assign in_payload  = (udp_len > 16'd8)                        // has a payload
                      && ({5'd0, idx} >= 16'(PAYLOAD_START))
                      && ({5'd0, idx} <= payload_end);

    // ------------------------------------------------------------------
    // Sequential: byte counter, check flag, length capture, output register
    // ------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            idx      <= '0;
            ok       <= 1'b1;
            udp_len  <= '0;
            m_tvalid <= 1'b0;
            m_tdata  <= '0;
            m_tlast  <= 1'b0;
        end else begin
            // default: no output this cycle
            m_tvalid <= 1'b0;
            m_tlast  <= 1'b0;

            if (s_tvalid) begin
                // capture the UDP length field (bytes 38-39, big-endian)
                if (idx == 11'd38) udp_len[15:8] <= s_tdata;
                if (idx == 11'd39) udp_len[7:0]  <= s_tdata;

                // forward payload bytes of valid frames
                if (ok && in_payload) begin
                    m_tvalid <= 1'b1;
                    m_tdata  <= s_tdata;
                    // end of payload; s_tlast also ends it so a truncated
                    // frame can never leave the output "open"
                    m_tlast  <= ({5'd0, idx} == payload_end) || s_tlast;
                end

                if (s_tlast) begin
                    // frame done: get ready for the next one (back-to-back OK)
                    idx     <= '0;
                    ok      <= 1'b1;
                    udp_len <= '0;
                end else begin
                    idx <= idx + 1'b1;
                    ok  <= ok & byte_ok;
                end
            end
        end
    end

endmodule
