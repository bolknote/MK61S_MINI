module tang_top #(
    parameter CLOCK_HZ = 27000000,
    parameter SDR_PHASE = "1000"
) (
    input wire clock27, host_rx,
    output wire host_tx, led_n,
    inout wire pico_link,
    output wire O_sdram_clk, O_sdram_cke, O_sdram_cs_n,
    output wire O_sdram_ras_n, O_sdram_cas_n, O_sdram_wen_n,
    output wire [10:0] O_sdram_addr,
    output wire [1:0] O_sdram_ba,
    output wire [3:0] O_sdram_dqm,
    inout wire [31:0] IO_sdram_dq
);
    wire clk, memory_clk, locked;
    localparam PLL_INPUT_DIVIDER = CLOCK_HZ == 27000000 ? 1 :
                                   CLOCK_HZ == 54000000 || CLOCK_HZ == 81000000 ? 0 : 2;
    localparam PLL_FEEDBACK = CLOCK_HZ == 99000000 ? 10 : CLOCK_HZ == 72000000 ? 7 :
                             CLOCK_HZ == 63000000 ? 6 : CLOCK_HZ == 45000000 ? 4 :
                             CLOCK_HZ == 36000000 ? 3 : CLOCK_HZ == 81000000 ? 2 : 1;
    localparam PLL_OUTPUT_DIVIDER = CLOCK_HZ == 27000000 ? 32 : CLOCK_HZ >= 63000000 ? 8 : 16;
    rPLL #(.FCLKIN("27"), .IDIV_SEL(PLL_INPUT_DIVIDER), .FBDIV_SEL(PLL_FEEDBACK),
           .ODIV_SEL(PLL_OUTPUT_DIVIDER),
           .PSDA_SEL(SDR_PHASE), .DUTYDA_SEL("1000"), .DEVICE("GW2A-18C")) pll (
        .CLKIN(clock27), .CLKOUT(clk), .CLKOUTP(memory_clk), .LOCK(locked),
        .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0), .FBDSEL(6'b0),
        .IDSEL(6'b0), .ODSEL(6'b0), .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0)
    );
    reg [7:0] reset_pipe = 0;
    always @(posedge clk) reset_pipe <= locked ? {reset_pipe[6:0], 1'b1} : 0;
    wire resetn = reset_pipe[7];

    wire [7:0] host_byte, pico_byte, outgoing;
    wire host_ready, pico_ready, host_busy, pico_busy, host_pop, pico_pop, host_push, pico_push;
    wire pico_tx;
    assign pico_link = resetn && pico_busy ? pico_tx : 1'bz;
    assign led_n = ~resetn;
    tang_uart #(.BIT_CLOCKS(CLOCK_HZ / 1000000)) host_uart (
        .clk(clk), .resetn(resetn), .rx(host_rx), .rx_enable(1'b1), .pop(host_pop),
        .tx_data(outgoing), .push(host_push), .rx_data(host_byte), .rx_ready(host_ready),
        .tx(host_tx), .tx_busy(host_busy)
    );
    tang_uart #(.BIT_CLOCKS(CLOCK_HZ / 1000000)) pico_uart (
        .clk(clk), .resetn(resetn), .rx(pico_link), .rx_enable(!pico_busy), .pop(pico_pop),
        .tx_data(outgoing), .push(pico_push), .rx_data(pico_byte), .rx_ready(pico_ready),
        .tx(pico_tx), .tx_busy(pico_busy)
    );

    wire link_req, link_wr, complete, test_dot_valid, dot_ready;
    wire [20:0] link_addr;
    wire [31:0] link_data, data_out, test_dot_weights;
    wire [63:0] test_dot_activations;
    wire signed [14:0] dot_result;
    wire model_start, model_reset, model_output, model_busy, model_done, model_req, model_wr, model_dot;
    wire [31:0] model_result, model_checksum, model_cycles, model_data, model_weights;
    wire [63:0] model_activations;
    wire [20:0] model_addr;
    wire [7:0] model_status;
    wire [15:0] model_token;
    tang_link_control #(.CLOCK_HZ(CLOCK_HZ)) transport (
        .clk(clk), .resetn(resetn), .host_input(host_byte), .pico_input(pico_byte),
        .host_available(host_ready), .pico_available(pico_ready), .host_tx_busy(host_busy), .pico_tx_busy(pico_busy),
        .host_pop(host_pop), .pico_pop(pico_pop), .host_push(host_push), .pico_push(pico_push),
        .serial_output(outgoing), .memory_request(link_req), .memory_write(link_wr),
        .memory_address(link_addr), .memory_data(link_data), .memory_complete(complete && !model_busy), .memory_result(data_out),
        .dot_valid(test_dot_valid), .dot_weights(test_dot_weights), .dot_activations(test_dot_activations),
        .dot_ready(dot_ready && !model_busy), .dot_result(dot_result), .model_start(model_start), .model_reset(model_reset),
        .model_token(model_token), .model_output(model_output),
        .model_done(model_done), .model_status(model_status), .model_result(model_result),
        .model_checksum(model_checksum), .model_cycles(model_cycles)
    );
`ifdef TANG_MODEL
    tang_model model (
        .clk(clk), .resetn(resetn), .start(model_start), .rewind(model_reset),
        .token(model_token), .output_logits(model_output), .busy(model_busy), .done(model_done),
        .status(model_status), .outcome(model_result), .checksum(model_checksum), .cycles(model_cycles),
        .memory_request(model_req), .memory_write(model_wr), .memory_address(model_addr), .memory_data(model_data),
        .memory_complete(complete && model_busy), .memory_result(data_out),
        .dot_valid(model_dot), .dot_weights(model_weights), .dot_activations(model_activations),
        .dot_ready(dot_ready && model_busy), .dot_result(dot_result)
    );
`else
    assign model_busy = 0;
    assign model_done = 1;
    assign model_status = 3;
    assign model_result = 0;
    assign model_checksum = 0;
    assign model_cycles = 0;
    assign model_req = 0;
    assign model_wr = 0;
    assign model_addr = 0;
    assign model_data = 0;
    assign model_dot = 0;
    assign model_weights = 0;
    assign model_activations = 0;
`endif
    tang_q4_dot dot (
        .clk(clk), .resetn(resetn), .valid(model_busy ? model_dot : test_dot_valid),
        .weights(model_busy ? model_weights : test_dot_weights),
        .activations(model_busy ? model_activations : test_dot_activations), .ready(dot_ready), .sum(dot_result)
    );
    tang_sdram #(.CLOCK_HZ(CLOCK_HZ)) memory (
        .clk(clk), .memory_clk(memory_clk), .resetn(resetn), .request(model_busy ? model_req : link_req),
        .write(model_busy ? model_wr : link_wr), .address(model_busy ? model_addr : link_addr),
        .data_in(model_busy ? model_data : link_data), .data_out(data_out), .complete(complete),
        .sd_clk(O_sdram_clk), .sd_cke(O_sdram_cke), .sd_cs_n(O_sdram_cs_n),
        .sd_ras_n(O_sdram_ras_n), .sd_cas_n(O_sdram_cas_n), .sd_we_n(O_sdram_wen_n),
        .sd_addr(O_sdram_addr), .sd_bank(O_sdram_ba), .sd_mask(O_sdram_dqm), .sd_dq(IO_sdram_dq)
    );
endmodule
