// Convert and scale up to six Q4 integer sums using the common FP32
// pipelines. A group retires before the sequencer advances to the next group,
// preserving the two rounded products and the accumulation order in each row.
module tang_matrix_scale #(
    parameter LANES = 6,
    parameter LANE_BITS = LANES <= 2 ? 1 : $clog2(LANES)
) (
    input wire clk, resetn, start,
    input wire [LANE_BITS-1:0] first_lane, last_lane,
    input wire [LANES*17-1:0] integer_sums,
    input wire [31:0] weight_scale,
    output wire [LANE_BITS-1:0] activation_lane, previous_lane,
    input wire [31:0] activation_scale, previous_sum,
    input wire [LANE_BITS-1:0] result_lane,
    output wire [31:0] result,
    output reg done,
    output wire mul_start,
    output wire [31:0] mul_a, mul_b,
    input wire mul_complete,
    input wire [31:0] mul_value,
    output reg add_start,
    output reg [31:0] add_a, add_b,
    input wire add_complete,
    input wire [31:0] add_value
);
    reg active, issuing;
    reg [LANE_BITS-1:0] issue_lane;
    wire [16:0] picked = integer_sums[17*issue_lane+:17];
    reg absolute_valid, shift_valid, weight_valid;
    reg [16:0] magnitude, magnitude_to_shift;
    reg [4:0] shift;
    wire [4:0] leading;
    wire [16:0] normalized = magnitude_to_shift << shift;
    reg [2:0] negative;
    reg [LANE_BITS-1:0] absolute_lane, shift_lane, weight_lane;
    reg [31:0] weight_operand;
    countLeadingZeros #(17,5) scan_integer(magnitude, leading);

    reg [LANE_BITS:0] multiply_tags [0:7];
    reg [LANE_BITS-1:0] add_tags [0:8];
    wire activation_return = multiply_tags[7][LANE_BITS];
    assign activation_lane = multiply_tags[7][LANE_BITS-1:0];
    assign previous_lane = activation_lane;
    reg activation_valid;
    reg [31:0] scaled_weight, activation_operand;
    reg [LANE_BITS-1:0] activation_input_lane, add_input_lane;
    assign mul_start = weight_valid || activation_valid;
    assign mul_a = activation_valid ? scaled_weight : weight_operand;
    assign mul_b = activation_valid ? activation_operand : weight_scale;
    reg [31:0] sums [0:LANES-1];
    assign result = sums[result_lane];

    integer i;
    always @(posedge clk) begin
        absolute_valid <= resetn && issuing;
        shift_valid <= resetn && absolute_valid;
        weight_valid <= resetn && shift_valid;
        if (issuing) begin
            absolute_lane <= issue_lane;
            magnitude <= picked[16] ? -picked : picked;
        end
        negative <= {negative[1:0],picked[16]};
        if (absolute_valid) begin
            shift_lane <= absolute_lane;
            magnitude_to_shift <= magnitude;
            shift <= leading;
        end
        if (shift_valid) begin
            weight_lane <= shift_lane;
            weight_operand <= magnitude_to_shift == 0 ? 32'b0 :
                {negative[1],8'd143-{3'b0,shift},normalized[15:0],7'b0};
        end
        multiply_tags[0] <= {activation_valid, activation_valid ? activation_input_lane : weight_lane};
        for (i=1; i<8; i=i+1) multiply_tags[i] <= multiply_tags[i-1];
        activation_valid <= resetn && active && mul_complete && !activation_return;
        if (active && mul_complete && !activation_return) begin
            activation_input_lane <= activation_lane;
            scaled_weight <= mul_value;
            activation_operand <= activation_scale;
        end

        add_start <= resetn && active && mul_complete && activation_return;
        if (active && mul_complete && activation_return) begin
            add_input_lane <= activation_lane;
            add_a <= previous_sum;
            add_b <= mul_value;
        end
        add_tags[0] <= add_input_lane;
        for (i=1; i<9; i=i+1) add_tags[i] <= add_tags[i-1];

        done <= 0;
        if (!resetn) begin
            active <= 0;
            issuing <= 0;
        end else if (start) begin
            active <= 1;
            issuing <= 1;
            issue_lane <= first_lane;
        end else begin
            if (issuing) begin
                if (issue_lane == last_lane) issuing <= 0;
                else issue_lane <= issue_lane + 1'b1;
            end
            if (active && add_complete) begin
                sums[add_tags[8]] <= add_value;
                if (add_tags[8] == last_lane) begin
                    active <= 0;
                    done <= 1;
                end
            end
        end
    end
endmodule
