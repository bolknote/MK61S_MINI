// There are at most four requests per Q4 block. The sequencer drains every
// reply before submitting the next block. Diagnostics allow one outstanding.
module tang_dot_fifo #(
    parameter WIDTH = 32, ADDRESS_BITS = 3, STREAM_READ = 0
) (
    input wire write_clk, write_resetn, push,
    input wire [WIDTH-1:0] write_data,
    input wire read_clk, read_resetn, pop,
    output wire available,
    output reg valid,
    output reg [WIDTH-1:0] read_data
);
    // The callers bound the outstanding words to the queue depth.
    (* ram_style = "block" *) reg [WIDTH-1:0] queue [0:(1<<ADDRESS_BITS)-1];
    reg [ADDRESS_BITS:0] written, written_gray, read_index, read_gray;
    reg read_pending;
    (* async_reg = "true" *) reg [ADDRESS_BITS:0] seen_first, seen;
    wire [ADDRESS_BITS:0] next_read = read_index + 1'b1;
    wire advance_read = STREAM_READ ? pop && available : read_pending;

    // Register the Gray encoding independently of the binary increment.
    always @(posedge write_clk) begin
        if (!write_resetn) begin
            written <= 0;
            written_gray <= 0;
        end else begin
            if (push) written <= written + 1'b1;
            written_gray <= written ^ (written >> 1);
        end
        if (write_resetn && push) queue[written[ADDRESS_BITS-1:0]] <= write_data;
    end

    assign available = read_gray != seen;
    always @(posedge read_clk) begin
        if (!read_resetn) begin
            seen_first <= 0;
            seen <= 0;
            read_index <= 0;
            read_gray <= 0;
            read_pending <= 0;
            valid <= 0;
        end else begin
            seen_first <= written_gray;
            seen <= seen_first;
            read_pending <= pop && available && !read_pending;
            valid <= advance_read;
            if (advance_read) begin
                read_index <= next_read;
                read_gray <= next_read ^ (next_read >> 1);
            end
        end
        if (advance_read) read_data <= queue[read_index[ADDRESS_BITS-1:0]];
    end
endmodule

// One DSP bank covers all positions by streaming one activation vector
// per fast clock. Quantization fills the other port of the activation BSRAM
// before the model submits a block. Both command and result queues cross
// clocks using dual port memory and Gray-coded pointers.
module tang_dot_cdc #(
    parameter LANES = 6,
    parameter LANE_BITS = LANES <= 2 ? 1 : $clog2(LANES)
) (
    input wire clk, resetn, fast_clk, fast_resetn,
    input wire write_activation,
    input wire [LANE_BITS+5:0] write_address,
    input wire [63:0] write_data,
    input wire request, test,
    input wire [31:0] weights,
    input wire [5:0] read_address,
    input wire [63:0] test_activations,
    output wire ready, test_ready,
    output wire [LANES*15-1:0] sums,
    output wire [14:0] test_sum
);
    localparam [LANE_BITS-1:0] LAST_LANE = LANE_BITS'(LANES-1);
    localparam [LANE_BITS+5:0] TEST_ADDRESS = {LANE_BITS+6{1'b1}};
    (* ram_style = "block" *) reg [63:0] activations [0:(1 << (LANE_BITS+6))-1];
    reg [63:0] fetched;
    always @(posedge clk) begin
        if (test) activations[TEST_ADDRESS] <= test_activations;
        else if (write_activation) activations[write_address] <= write_data;
    end

    wire [38:0] command;
    wire have_command, command_valid;
    reg [38:0] staged_command;
    reg command_pending;
    reg active, testing;
    reg [LANE_BITS-1:0] issue_lane;
    reg [5:0] vector_address;
    reg [31:0] active_weights, fetched_weights;
    reg fetch_valid, fetch_last, fetch_test;
    wire issue_last = active && (testing || issue_lane == LAST_LANE);
    wire issue_penultimate = active && !testing && LANES > 1 && issue_lane == LAST_LANE-1'b1;
    // Fetch the next command a lane early, allowing a register after the
    // FIFO's BRAM output without delaying the next weight word.
    wire pop = have_command && !command_valid && !command_pending &&
               (!active || issue_last || issue_penultimate);
    tang_dot_fifo #(.WIDTH(39)) commands (
        .write_clk(clk), .write_resetn(resetn), .push(test || request),
        .write_data({test,weights,read_address}), .read_clk(fast_clk),
        .read_resetn(fast_resetn), .pop(pop), .available(have_command),
        .valid(command_valid), .read_data(command)
    );
    always @(posedge fast_clk) begin
        staged_command <= command;
        command_pending <= fast_resetn && command_valid;
        if (!fast_resetn) active <= 0;
        else if (command_pending) begin
            active <= 1;
            testing <= staged_command[38];
            active_weights <= staged_command[37:6];
            issue_lane <= staged_command[38] ? TEST_ADDRESS[LANE_BITS+5:6] : 0;
            vector_address <= staged_command[38] ? TEST_ADDRESS[5:0] : staged_command[5:0];
        end else if (active) begin
            if (issue_last) active <= 0;
            else issue_lane <= issue_lane + 1'b1;
        end

        fetch_valid <= fast_resetn && active;
        fetch_last <= issue_last;
        fetch_test <= testing;
        fetched_weights <= active_weights;
        if (active) fetched <= activations[{issue_lane,vector_address}];
    end

    reg [31:0] dot_weights;
    (* keep *) reg [63:0] dot_activations;
    reg dot_start;
    reg [6:0] last_pipe, test_pipe;
    always @(posedge fast_clk) begin
        dot_weights <= fetched_weights;
        dot_activations <= fetched;
        dot_start <= fetch_valid;
        last_pipe <= {last_pipe[5:0],fetch_last};
        test_pipe <= {test_pipe[5:0],fetch_test};
    end

    wire sum_valid;
    wire [14:0] sum;
    tang_dot_dsp dot(fast_clk, fast_resetn, dot_start, dot_weights, dot_activations, sum_valid, sum);
    localparam PREVIOUS_BITS = (LANES == 1 ? 1 : LANES - 1) * 15;
    reg [PREVIOUS_BITS-1:0] earlier_sums;
    always @(posedge fast_clk)
        if (sum_valid) earlier_sums <= PREVIOUS_BITS'({sum,earlier_sums} >> 15);
    wire [LANES*15-1:0] collected_sums = LANES == 1 ? sum : {sum,earlier_sums};

    wire result_valid, result_test;
    reg result_pending;
    reg [LANES*15:0] result_packet;
    // End the DSP pipeline before the FIFO's address and write enable.
    always @(posedge fast_clk) begin
        result_pending <= fast_resetn && sum_valid && last_pipe[6];
        result_packet <= {test_pipe[6],collected_sums};
    end
    tang_dot_fifo #(.WIDTH(LANES*15+1)) results (
        .write_clk(fast_clk), .write_resetn(fast_resetn), .push(result_pending),
        .write_data(result_packet), .read_clk(clk), .read_resetn(resetn),
        .pop(1'b1), .available(), .valid(result_valid), .read_data({result_test,sums})
    );
    assign ready = result_valid && !result_test;
    assign test_ready = result_valid && result_test;
    assign test_sum = sums[LANES*15-1 -: 15];
endmodule

module tang_dot_dsp (
    input wire clk, resetn, start,
    input wire [31:0] weights,
    input wire [63:0] activations,
    output wire ready,
    output reg signed [14:0] dot
);
    wire signed [11:0] products[0:7];
    reg signed [12:0] pairs[0:3];
    reg signed [13:0] left, right;
    reg [5:0] valid;
    assign ready = valid[5];
    always @(posedge clk) begin
        valid <= resetn ? {valid[4:0],start} : 0;
        left <= pairs[0] + pairs[1];
        right <= pairs[2] + pairs[3];
        dot <= left + right;
    end
    genvar i;
    generate for (i=0;i<4;i=i+1) begin: pair
        always @(posedge clk) pairs[i] <= products[2*i] + products[2*i+1];
    end endgenerate
    generate for (i=0;i<8;i=i+1) begin: mul
        wire [3:0] w = weights[4*i +: 4] ^ 4'h8;
        wire [7:0] a = activations[8*i +: 8];
`ifdef TANG_SIM
        reg signed [11:0] ab, pipe, out;
        always @(posedge clk) begin
            ab <= $signed(w) * $signed(a);
            pipe <= ab;
            out <= pipe;
        end
        assign products[i] = out;
`else
        wire [17:0] product;
        MULT9X9 #(.AREG(1'b1),.BREG(1'b1),.PIPE_REG(1'b1),.OUT_REG(1'b1)) multiply(
            .A({{5{w[3]}},w}), .B({a[7],a}), .DOUT(product), .SOA(), .SOB(),
            .ASIGN(1'b1), .BSIGN(1'b1), .ASEL(1'b0), .BSEL(1'b0), .SIA(9'd0), .SIB(9'd0),
            .CLK(clk), .CE(1'b1), .RESET(1'b0)
        );
        assign products[i] = product[11:0];
`endif
    end endgenerate
endmodule
