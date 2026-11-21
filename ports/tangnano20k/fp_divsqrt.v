// Restoring binary division and square root for recoded binary32 operands.
// Keep the trial remainder and significand digits in registers. Both
// operations produce 24 significand bits, a guard bit, and an exact sticky bit.
module tang_fp_divsqrt (
    input wire clk, resetn, start, sqrt,
    input wire [32:0] a, b,
    output wire complete,
    output reg [40:0] raw
);
    localparam IDLE=0, PREPARE=1, INITIALIZE=2, DIGITS=3, RETURN=4;
    reg [2:0] stage;
    reg root;
    reg [8:0] a_exponent, b_exponent;
    reg [23:0] a_significand, denominator;
    reg signed [10:0] exponent_difference;
    reg shift_numerator;
    reg [49:0] radicand;
    reg [26:0] trial_remainder;
    reg [24:0] digits;
    reg [4:0] remaining;

    wire a_zero = a[31:29] == 3'b000, b_zero = b[31:29] == 3'b000;
    wire a_inf = a[31:29] == 3'b110, b_inf = b[31:29] == 3'b110;
    wire a_nan = a[31:29] == 3'b111, b_nan = b[31:29] == 3'b111;
    wire is_nan = sqrt ? a_nan || (a[32] && !a_zero) :
                         a_nan || b_nan || (a_inf && b_inf) || (a_zero && b_zero);
    wire is_inf = a_inf || (!sqrt && b_zero);
    wire is_zero = a_zero || (!sqrt && b_inf);
    wire [49:0] root_input = a_exponent[0] ? {a_significand,26'b0} : {1'b0,a_significand,25'b0};
    wire signed [10:0] div_exponent = exponent_difference - $signed({10'b0,shift_numerator});

    wire [26:0] trial_term = root ? {digits,2'b01} : {3'b0,denominator};
    wire [27:0] difference = {1'b0,trial_remainder} - {1'b0,trial_term};
    wire take_digit = !difference[27];
    wire [26:0] remainder = take_digit ? difference[26:0] : trial_remainder;
    wire [24:0] next_digits = {digits[23:0],take_digit};
    wire sticky = take_digit ? (trial_remainder != trial_term) : (trial_remainder != 0);
    assign complete = stage == RETURN;

    always @(posedge clk) begin
        if (!resetn) stage <= IDLE;
        else case (stage)
            IDLE: if (start) begin
                raw <= {is_nan,is_inf,is_zero,a[32] ^ (!sqrt && b[32]),37'b0};
                root <= sqrt;
                a_exponent <= a[31:23];
                b_exponent <= b[31:23];
                a_significand <= {1'b1,a[22:0]};
                denominator <= {1'b1,b[22:0]};
                stage <= is_nan || is_inf || is_zero ? RETURN : PREPARE;
            end
            PREPARE: begin
                exponent_difference <= $signed({2'b0,a_exponent}) -
                                       $signed({2'b0,b_exponent}) + 11'sd256;
                shift_numerator <= a_significand < denominator;
                stage <= INITIALIZE;
            end
            INITIALIZE: begin
                if (root) begin
                    raw[36:27] <= 10'd128 + {2'b0,a_exponent[8:1]};
                    trial_remainder <= {25'b0,root_input[49:48]};
                    radicand <= {root_input[47:0],2'b0};
                end else begin
                    raw[36:27] <= div_exponent > 11'sd511 ? 10'd511 : div_exponent[9:0];
                    trial_remainder <= shift_numerator ? {2'b0,a_significand,1'b0} : {3'b0,a_significand};
                end
                digits <= 0;
                remaining <= 25;
                stage <= DIGITS;
            end
            DIGITS: begin
                digits <= next_digits;
                remaining <= remaining - 1'b1;
                trial_remainder <= root ? {remainder[24:0],radicand[49:48]} : {remainder[25:0],1'b0};
                radicand <= {radicand[47:0],2'b0};
                if (remaining == 1) begin
                    raw[26:0] <= {1'b0,next_digits,sticky};
                    stage <= RETURN;
                end
            end
            RETURN: stage <= IDLE;
            default: stage <= IDLE;
        endcase
    end
endmodule
