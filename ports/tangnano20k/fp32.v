// The board's floating point path preserves the order and rounding of the
// PicoCalc implementation. Multiply and add are separate operations.
module tang_fp32 (
    input wire clk, resetn, start,
    input wire [2:0] operation,
    input wire [31:0] a, b,
    output wire complete,
    output reg [31:0] result,
    // The attention sequencer can use the adder while the scalar unit
    // multiplies the next pair. It drains these additions before using ADD.
    input wire add_start,
    input wire [31:0] add_a, add_b,
    output wire add_complete,
    output wire [31:0] add_value,
    input wire mul_start,
    input wire [31:0] mul_a, mul_b,
    output wire mul_complete,
    output wire [31:0] mul_value
);
    localparam ADD=0, SUB=1, MUL=2, DIV=3, SQRT=4, INTEGER=5, EXP=6;
    localparam IDLE=0, CONVERT=1, CALCULATE=2, WAIT_DIV=3, ROUND_PACK=4, RETURN=5, WAIT_EXP=6,
        ROUND_PREPARE=7, WAIT_ADD=8, INTEGER_SCAN=9, INTEGER_PACK=10, ROUND_SHIFT=11, ROUND_SUBNORMAL=12,
        CONVERT_SUBNORMAL=13, START_EXP=14;
    reg [3:0] step;
    reg [2:0] op;
    reg [31:0] raw_a, raw_b;
    reg [32:0] rec_a, rec_b;
    wire subnormal_a = raw_a[30:23] == 0 && raw_a[22:0] != 0;
    wire subnormal_b = raw_b[30:23] == 0 && raw_b[22:0] != 0;
    wire [4:0] zeros_a, zeros_b;
    reg [4:0] normalize_a, normalize_b;
    wire [32:0] decoded_a, decoded_b;
    wire stream_decoded;
    wire [32:0] stream_a, stream_b;
    wire [41:0] raw_mul;
    wire [40:0] raw_div;
    reg [41:0] unrounded;
    wire [31:0] exp_value;
    wire exp_complete, div_complete;
    // The raw significand has two integer bits and a guard and sticky bit.
    // Normalize before rounding; the common normal case needs no barrel shift.
    wire normalize = unrounded[26];
    wire signed [10:0] biased = $signed({unrounded[36],unrounded[36:27]}) +
                                $signed({10'b0,normalize}) - 11'sd129;
    wire [25:0] significand = normalize ? {unrounded[26:2],|unrounded[1:0]} : unrounded[25:0];
    reg [25:0] denorm_sig, denorm_aligned, discard_mask;
    reg [4:0] denorm_shift;
    reg [30:0] rounded_bits;
    reg round_up;
    // The integer input is a Q4 code or the sum of 32 Q4×INT8 products.
    // Seventeen signed bits cover the entire range, exactly in binary32.
    reg [16:0] int_magnitude;
    reg [4:0] int_shift;
    wire [4:0] leading;
    wire [16:0] normalized_integer = int_magnitude << int_shift;
    countLeadingZeros #(17,5) scan_integer(int_magnitude, leading);
    assign complete = step == RETURN;

    countLeadingZeros #(23,5) scan_a(raw_a[22:0],zeros_a);
    countLeadingZeros #(23,5) scan_b(raw_b[22:0],zeros_b);
    tang_fp_recode recode_a(raw_a, normalize_a, decoded_a);
    tang_fp_recode recode_b(raw_b, normalize_b, decoded_b);
    wire scalar_add = start && step == IDLE && (operation == ADD || operation == SUB);
    reg adder_start, adder_subtract;
    reg [31:0] adder_a, adder_b;
    // Separate the sequencer's operand mux from the FP32 magnitude comparison.
    always @(posedge clk) begin
        adder_start <= resetn && (add_start || scalar_add);
        adder_subtract <= scalar_add && operation == SUB;
        adder_a <= add_start ? add_a : a;
        adder_b <= add_start ? add_b : b;
    end
    tang_fp_add adder(clk, resetn, adder_start, adder_subtract,
                      adder_a, adder_b, add_complete, add_value);
    // The scalar and stream paths share the DSP. The sequencer drains the
    // stream before starting another scalar operation.
    tang_fp_mul_stream stream(clk, resetn, mul_start, mul_a, mul_b,
        stream_decoded, stream_a, stream_b, raw_mul, mul_complete, mul_value);
    mulRecFNToRaw #(8,24) multiplier(1'b1, rec_a, rec_b,
        raw_mul[41], raw_mul[40], raw_mul[39], raw_mul[38], raw_mul[37], raw_mul[36:27], raw_mul[26:0]);
    tang_fp_divsqrt divider(
        .clk(clk), .resetn(resetn), .start(step == CALCULATE && (op == DIV || op == SQRT)),
        .sqrt(op == SQRT), .a(rec_a), .b(rec_b), .complete(div_complete), .raw(raw_div)
    );
    // Use the captured scalar operand before the exponential's range test.
    // Attention scores can arrive from BRAM through the shared operand mux.
    tang_exp32 exponential(clk, resetn, step == START_EXP, raw_a, exp_complete, exp_value);

    wire scalar_decoded = step == CONVERT_SUBNORMAL ||
                          (step == CONVERT && !subnormal_a && !subnormal_b);
    always @(posedge clk) begin
        if (stream_decoded || scalar_decoded) begin
            rec_a <= stream_decoded ? stream_a : decoded_a;
            rec_b <= stream_decoded ? stream_b : decoded_b;
        end
    end

    always @(posedge clk) begin
        if (!resetn) step <= IDLE;
        else case (step)
            IDLE: if (start) begin
                raw_a <= a;
                raw_b <= b;
                op <= operation;
                if (operation == INTEGER) begin
                    int_magnitude <= a[16] ? -a[16:0] : a[16:0];
                    step <= INTEGER_SCAN;
                end else step <= operation == EXP ? START_EXP : operation <= SUB ? WAIT_ADD : CONVERT;
            end
            INTEGER_SCAN: begin int_shift <= leading; step <= INTEGER_PACK; end
            INTEGER_PACK: begin
                result <= int_magnitude == 0 ? 32'b0 :
                          {raw_a[16], 8'd143 - {3'b0,int_shift}, normalized_integer[15:0], 7'b0};
                step <= RETURN;
            end
            CONVERT, CONVERT_SUBNORMAL: begin
                if (step == CONVERT && (subnormal_a || subnormal_b)) begin
                    normalize_a <= zeros_a;
                    normalize_b <= zeros_b;
                    step <= CONVERT_SUBNORMAL;
                end else step <= CALCULATE;
            end
            CALCULATE: begin
                if (op == DIV || op == SQRT) step <= WAIT_DIV;
                else begin unrounded <= raw_mul; step <= ROUND_PREPARE; end
            end
            WAIT_DIV: if (div_complete) begin
                unrounded <= {1'b0,raw_div}; step <= ROUND_PREPARE;
            end
            ROUND_PREPARE: begin
                if (unrounded[41] || unrounded[40]) begin
                    result <= 32'h7fc00000; step <= RETURN;
                end else if (unrounded[39]) begin
                    result <= {unrounded[37],31'h7f800000}; step <= RETURN;
                end else if (unrounded[38] || biased < -11'sd23) begin
                    result <= {unrounded[37],31'b0}; step <= RETURN;
                end else if (biased >= 11'sd255) begin
                    result <= {unrounded[37],31'h7f800000}; step <= RETURN;
                end else if (biased > 0) begin
                    rounded_bits <= {biased[7:0],significand[24:2]};
                    round_up <= significand[1] && (significand[0] || significand[2]);
                    step <= ROUND_PACK;
                end else begin
                    denorm_sig <= significand;
                    denorm_shift <= 5'd1 - biased[4:0];
                    step <= ROUND_SHIFT;
                end
            end
            ROUND_SHIFT: begin
                denorm_aligned <= denorm_sig >> denorm_shift;
                discard_mask <= ~(26'h3ffffff << denorm_shift);
                step <= ROUND_SUBNORMAL;
            end
            ROUND_SUBNORMAL: begin
                rounded_bits <= {8'b0,denorm_aligned[24:2]};
                round_up <= denorm_aligned[1] &&
                    (denorm_aligned[2] || denorm_aligned[0] || |(denorm_sig & discard_mask));
                step <= ROUND_PACK;
            end
            ROUND_PACK: begin
                // A carry from the fraction increments the exponent, including
                // promotion of a subnormal to the smallest normal number.
                result <= {unrounded[37],rounded_bits + {30'b0,round_up}};
                step <= RETURN;
            end
            START_EXP: step <= WAIT_EXP;
            WAIT_EXP: if (exp_complete) begin result <= exp_value; step <= RETURN; end
            WAIT_ADD: if (add_complete) begin result <= add_value; step <= RETURN; end
            RETURN: step <= IDLE;
            default: step <= IDLE;
        endcase
    end
endmodule

module tang_fp_recode (
    input wire [31:0] value,
    input wire [4:0] leading_zeros,
    output wire [32:0] recoded
);
    reg [8:0] exponent;
    reg [22:0] fraction;
    always @* begin
        fraction = value[22:0];
        case (value[30:23])
            0: begin
                exponent = 0;
                if (fraction != 0) begin
                    exponent = 9'd129 - {4'b0,leading_zeros};
                    fraction = (fraction << leading_zeros) << 1;
                end
            end
            255: exponent = fraction == 0 ? 9'h180 : 9'h1c0;
            default: exponent = 9'd129 + {1'b0,value[30:23]};
        endcase
    end
    assign recoded = {value[31],exponent,fraction};
endmodule

// Accept one IEEE binary32 pair per cycle. The product is rounded before it
// reaches the attention adder, including when the product is subnormal.
module tang_fp_mul_stream (
    input wire clk, resetn, start,
    input wire [31:0] a, b,
    output wire operands_ready,
    output wire [32:0] decoded_a, decoded_b,
    // The shared multiplier latches these operands on operands_ready.
    input wire [41:0] raw_product,
    output wire complete,
    output reg [31:0] result
);
    reg [7:0] valid;
    reg [31:0] captured_a, captured_b, raw_a, raw_b;
    wire [4:0] zeros_a, zeros_b;
    reg [4:0] normalize_a, normalize_b;
    reg [41:0] unrounded;
    countLeadingZeros #(23,5) scan_a(captured_a[22:0],zeros_a);
    countLeadingZeros #(23,5) scan_b(captured_b[22:0],zeros_b);
    tang_fp_recode recode_a(raw_a, normalize_a, decoded_a);
    tang_fp_recode recode_b(raw_b, normalize_b, decoded_b);
    assign operands_ready = valid[1];

    wire normalize = unrounded[26];
    wire signed [10:0] biased = $signed({unrounded[36],unrounded[36:27]}) +
                                $signed({10'b0,normalize}) - 11'sd129;
    reg [25:0] significand, aligned;
    reg [4:0] shift;
    reg discarded;
    reg [7:0] exponent, aligned_exponent;
    reg [2:0] negative, nan, infinite, zero;
    reg [30:0] rounded_bits;
    reg round_up;
    assign complete = valid[7];

    always @(posedge clk) begin
        valid <= resetn ? {valid[6:0],start} : 0;
        if (start) begin captured_a <= a; captured_b <= b; end
        if (valid[0]) begin
            raw_a <= captured_a; raw_b <= captured_b;
            normalize_a <= zeros_a; normalize_b <= zeros_b;
        end
        if (valid[2]) unrounded <= raw_product;
        if (valid[3]) begin
            significand <= normalize ? {unrounded[26:2],|unrounded[1:0]} : unrounded[25:0];
            exponent <= biased > 0 ? biased[7:0] : 8'b0;
            shift <= biased > 0 ? 5'b0 : 5'd1 - biased[4:0];
        end
        negative <= {negative[1:0],unrounded[37]};
        nan <= {nan[1:0],unrounded[41] || unrounded[40]};
        infinite <= {infinite[1:0],unrounded[39] || biased >= 11'sd255};
        zero <= {zero[1:0],!unrounded[39] && (unrounded[38] || biased < -11'sd23)};
        if (valid[4]) begin
            aligned <= significand >> shift;
            discarded <= |(significand & ~(26'h3ffffff << shift));
            aligned_exponent <= exponent;
        end
        if (valid[5]) begin
            rounded_bits <= {aligned_exponent,aligned[24:2]};
            round_up <= aligned[1] && (aligned[2] || aligned[0] || discarded);
        end
        if (valid[6]) begin
            if (nan[2]) result <= 32'h7fc00000;
            else if (zero[2]) result <= {negative[2],31'b0};
            else if (infinite[2]) result <= {negative[2],31'h7f800000};
            else result <= {negative[2],rounded_bits + {30'b0,round_up}};
        end
    end
endmodule
