// The board's floating point path preserves the order and rounding of the
// PicoCalc implementation. Multiply and add are separate operations.
module tang_fp32 (
    input wire clk, resetn, start,
    input wire [2:0] operation,
    input wire [31:0] a, b,
    output wire complete,
    output reg [31:0] result
);
    localparam ADD=0, SUB=1, MUL=2, DIV=3, SQRT=4, INTEGER=5, EXP=6;
    localparam IDLE=0, CONVERT=1, CALCULATE=2, WAIT_DIV=3, CONVERT_BACK=4, RETURN=5, WAIT_EXP=6,
        ROUND=7, WAIT_ADD=8, INTEGER_SCAN=9, INTEGER_PACK=10;
    reg [3:0] step;
    reg [2:0] op;
    reg [31:0] raw_a, raw_b;
    reg [32:0] rec_a, rec_b, calculated;
    wire [32:0] encode_a, encode_b, rounded;
    wire [41:0] raw_mul, raw_div;
    reg [41:0] unrounded;
    wire div_accept, div_complete, div_infinite;
    reg unrounded_infinite;
    wire [31:0] float_value, exp_value, add_value;
    wire exp_complete, add_complete;
    // The integer input is a Q4 code or the sum of 32 Q4×INT8 products.
    // Seventeen signed bits cover the entire range, exactly in binary32.
    reg [16:0] int_magnitude;
    reg [4:0] int_shift;
    wire [4:0] leading;
    wire [16:0] normalized_integer = int_magnitude << int_shift;
    countLeadingZeros #(17,5) scan_integer(int_magnitude, leading);
    assign complete = step == RETURN;

    fNToRecFN #(8,24) encode_first(raw_a, encode_a);
    fNToRecFN #(8,24) encode_second(raw_b, encode_b);
    recFNToFN #(8,24) decode(calculated, float_value);
    tang_fp_add adder(clk, resetn, start && step == IDLE && (operation == ADD || operation == SUB),
                      operation == SUB, a, b, add_complete, add_value);
    mulRecFNToRaw #(8,24) multiplier(1'b1, rec_a, rec_b,
        raw_mul[41], raw_mul[40], raw_mul[39], raw_mul[38], raw_mul[37], raw_mul[36:27], raw_mul[26:0]);
    roundRawFNToRecFN #(8,24,0) rounder(1'b1, unrounded[41], unrounded_infinite, unrounded[40],
        unrounded[39], unrounded[38], unrounded[37], unrounded[36:27], unrounded[26:0], 3'b0, rounded, );
    divSqrtRecFNToRaw_small #(8,24,0) divider(
        .nReset(resetn), .clock(clk), .control(1'b1), .inReady(div_accept),
        .inValid(step == CALCULATE && (op == DIV || op == SQRT)), .sqrtOp(op == SQRT),
        .a(rec_a), .b(rec_b), .roundingMode(3'b0), .outValid(div_complete),
        .sqrtOpOut(), .roundingModeOut(), .invalidExc(raw_div[41]), .infiniteExc(div_infinite),
        .out_isNaN(raw_div[40]), .out_isInf(raw_div[39]), .out_isZero(raw_div[38]),
        .out_sign(raw_div[37]), .out_sExp(raw_div[36:27]), .out_sig(raw_div[26:0])
    );
    tang_exp32 exponential(clk, resetn, start && step == IDLE && operation == EXP,
                           a, exp_complete, exp_value);

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
                end else step <= operation == EXP ? WAIT_EXP : operation <= SUB ? WAIT_ADD : CONVERT;
            end
            INTEGER_SCAN: begin int_shift <= leading; step <= INTEGER_PACK; end
            INTEGER_PACK: begin
                result <= int_magnitude == 0 ? 32'b0 :
                          {raw_a[16], 8'd143 - {3'b0,int_shift}, normalized_integer[15:0], 7'b0};
                step <= RETURN;
            end
            CONVERT: begin rec_a <= encode_a; rec_b <= encode_b; step <= CALCULATE; end
            CALCULATE: begin
                if (op == DIV || op == SQRT) begin
                    if (div_accept) step <= WAIT_DIV;
                end else begin unrounded <= raw_mul; unrounded_infinite <= 0; step <= ROUND; end
            end
            ROUND: begin calculated <= rounded; step <= CONVERT_BACK; end
            WAIT_DIV: if (div_complete) begin
                unrounded <= raw_div; unrounded_infinite <= div_infinite; step <= ROUND;
            end
            WAIT_EXP: if (exp_complete) begin result <= exp_value; step <= RETURN; end
            WAIT_ADD: if (add_complete) begin result <= add_value; step <= RETURN; end
            CONVERT_BACK: begin result <= float_value; step <= RETURN; end
            RETURN: step <= IDLE;
            default: step <= IDLE;
        endcase
    end
endmodule
