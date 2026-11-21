module tang_top #(
    parameter CLOCK_HZ = 27000000,
    parameter SDR_PHASE = "1000",
    parameter HALF_SDRAM_CLOCK = 0,
    parameter SDRAM_DIVIDER = HALF_SDRAM_CLOCK ? 2 : 1,
    parameter PREFILL_LANES = 4,
    parameter DSP_CLOCK_HZ = 0,
    parameter SDRAM_FROM_DSP = 0
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
    localparam PLL_INPUT_DIVIDER = CLOCK_HZ == 96000000 || CLOCK_HZ == 102000000 ? 8 : CLOCK_HZ == 27000000 ? 1 :
                                   CLOCK_HZ == 54000000 || CLOCK_HZ == 81000000 ? 0 : 2;
    localparam PLL_FEEDBACK = CLOCK_HZ == 108000000 ? 11 : CLOCK_HZ == 102000000 ? 33 :
                             CLOCK_HZ == 99000000 ? 10 : CLOCK_HZ == 96000000 ? 31 : CLOCK_HZ == 90000000 ? 9 :
                             CLOCK_HZ == 72000000 ? 7 :
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
    wire dsp_locked;
    reg [7:0] reset_pipe = 0;
    always @(posedge clk) reset_pipe <= locked && dsp_locked ? {reset_pipe[6:0], 1'b1} : 0;
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

    wire link_req, link_wr, complete, test_dot_valid;
    wire [20:0] link_addr;
    wire [31:0] link_data, data_out, test_dot_weights;
    wire [63:0] test_dot_activations;
    wire [PREFILL_LANES-1:0] dot_ready;
    wire [PREFILL_LANES*15-1:0] dot_results;
    wire diagnostic_ready;
    wire [14:0] diagnostic_result;
    wire model_start, model_reset, model_output, model_busy, model_done, model_req, model_wr, model_burst, model_dot;
    wire [31:0] model_result, model_checksum, model_cycles, model_data, model_weights;
    wire [PREFILL_LANES*64-1:0] model_activations;
    wire [PREFILL_LANES*32-1:0] model_checksums;
    wire [20:0] model_addr;
    wire [4:0] model_read_extra;
    wire [7:0] model_status;
    wire model_verify_pair;
    wire [4:0] model_allowed_second;
    wire [15:0] model_first_prediction;
    wire [PREFILL_LANES*16-1:0] model_tokens;
    wire [2:0] model_count;
    wire [4:0] model_allowed;
    wire [10:0] model_seek;
    wire [5:0] dot_activation_index;
    wire quantized_write;
    wire [$clog2(PREFILL_LANES*64)-1:0] quantized_address;
    wire [63:0] quantized_data;
`ifdef TANG_MODEL
    localparam MODEL_ENABLED = 1;
`else
    localparam MODEL_ENABLED = 0;
`endif
    tang_link_control #(.CLOCK_HZ(CLOCK_HZ), .MODEL_ENABLED(MODEL_ENABLED), .PREFILL_LANES(PREFILL_LANES)) transport (
        .clk(clk), .resetn(resetn), .host_input(host_byte), .pico_input(pico_byte),
        .host_available(host_ready), .pico_available(pico_ready), .host_tx_busy(host_busy), .pico_tx_busy(pico_busy),
        .host_pop(host_pop), .pico_pop(pico_pop), .host_push(host_push), .pico_push(pico_push),
        .serial_output(outgoing), .memory_request(link_req), .memory_write(link_wr),
        .memory_address(link_addr), .memory_data(link_data), .memory_complete(complete && !model_busy), .memory_result(data_out),
        .dot_valid(test_dot_valid), .dot_weights(test_dot_weights), .dot_activations(test_dot_activations),
        .dot_ready(diagnostic_ready), .dot_result(diagnostic_result),
        .model_start(model_start), .model_reset(model_reset),
        .model_tokens(model_tokens), .model_count(model_count), .model_output(model_output),
        .model_allowed(model_allowed), .model_allowed_second(model_allowed_second),
        .model_verify_pair(model_verify_pair), .model_first_prediction(model_first_prediction), .model_seek(model_seek),
        .model_done(model_done), .model_status(model_status), .model_result(model_result),
        .model_checksum(model_checksum), .model_checksums(model_checksums), .model_cycles(model_cycles)
    );
`ifdef TANG_MODEL
    tang_model #(.PREFILL_LANES(PREFILL_LANES)) model (
        .clk(clk), .resetn(resetn), .start(model_start), .rewind(model_reset),
        .tokens(model_tokens), .token_count(model_count), .output_logits(model_output), .verify_pair(model_verify_pair), .busy(model_busy), .done(model_done),
        .allowed_count(model_allowed), .allowed_second(model_allowed_second), .seek_position(model_seek),
        .status(model_status), .outcome(model_result), .checksum(model_checksum), .cycles(model_cycles),
        .position_checksums(model_checksums), .first_prediction(model_first_prediction),
        .memory_request(model_req), .memory_write(model_wr), .memory_burst(model_burst),
        .memory_read_extra(model_read_extra),
        .memory_address(model_addr), .memory_data(model_data),
        .memory_complete(complete && model_busy), .memory_result(data_out),
        .dot_valid(model_dot), .dot_weights(model_weights), .dot_activations(model_activations),
        .dot_activation_index(dot_activation_index), .activation_write(quantized_write),
        .activation_write_index(quantized_address), .activation_write_data(quantized_data),
        .dot_ready(dot_ready[0] && model_busy), .dot_results(dot_results)
    );
`else
    assign model_busy = 0;
    assign model_done = 1;
    assign model_status = 3;
    assign model_first_prediction = 0;
    assign model_result = 0;
    assign model_checksum = 0;
    assign model_checksums = 0;
    assign model_cycles = 0;
    assign model_req = 0;
    assign model_wr = 0;
    assign model_burst = 0;
    assign model_read_extra = 0;
    assign model_addr = 0;
    assign model_data = 0;
    assign model_dot = 0;
    assign model_weights = 0;
    assign model_activations = 0;
    assign dot_activation_index = 0;
    assign quantized_write = 0;
    assign quantized_address = 0;
    assign quantized_data = 0;
`endif
    wire [31:0] dot_weights = model_busy ? model_weights : test_dot_weights;
    wire divided_dsp_clk;
    genvar p;
    generate if (DSP_CLOCK_HZ != 0) begin: separate_dsp
        localparam INPUT_DIVIDE = DSP_CLOCK_HZ == 252000000 || DSP_CLOCK_HZ == 198000000 ? 2 : 0;
        localparam FEEDBACK = DSP_CLOCK_HZ == 252000000 ? 27 : DSP_CLOCK_HZ == 270000000 ? 9 :
                              DSP_CLOCK_HZ == 216000000 ? 7 : DSP_CLOCK_HZ == 243000000 ? 8 :
                              DSP_CLOCK_HZ == 198000000 ? 21 : DSP_CLOCK_HZ == 162000000 ? 5 : 6;
        wire fast_clk;
        rPLL #(.FCLKIN("27"), .IDIV_SEL(INPUT_DIVIDE), .FBDIV_SEL(FEEDBACK), .ODIV_SEL(4), .DEVICE("GW2A-18C")) fast_pll (
            .CLKIN(clock27), .CLKOUT(fast_clk), .CLKOUTP(), .CLKOUTD3(divided_dsp_clk),
            .LOCK(dsp_locked), .RESET(1'b0),
            .RESET_P(1'b0), .CLKFB(1'b0), .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0), .PSDA(4'b0),
            .DUTYDA(4'b0), .FDLY(4'b0)
        );
        reg [7:0] fast_reset_pipe = 0;
        always @(posedge fast_clk) fast_reset_pipe <= locked && dsp_locked ? {fast_reset_pipe[6:0], 1'b1} : 0;
        if (PREFILL_LANES > 1) assign dot_ready[PREFILL_LANES-1:1] = 0;
        tang_dot_cdc #(.LANES(PREFILL_LANES)) dot (
            .clk(clk), .resetn(resetn), .fast_clk(fast_clk), .fast_resetn(fast_reset_pipe[7]),
            .write_activation(quantized_write), .write_address(quantized_address), .write_data(quantized_data),
            .request(model_dot), .test(test_dot_valid && !model_busy), .weights(dot_weights),
            .read_address(dot_activation_index), .test_activations(test_dot_activations),
            .ready(dot_ready[0]), .test_ready(diagnostic_ready), .sums(dot_results), .test_sum(diagnostic_result)
        );
    end else begin: direct_dsp
        assign dsp_locked = 1;
        assign divided_dsp_clk = 0;
        assign diagnostic_ready = dot_ready[0] && !model_busy;
        assign diagnostic_result = dot_results[14:0];
        for (p=0; p<PREFILL_LANES; p=p+1) begin: position_dot
            wire valid = p == 0 && !model_busy ? test_dot_valid : model_dot;
            wire [63:0] activation = p == 0 && !model_busy ? test_dot_activations : model_activations[p*64 +: 64];
            tang_q4_dot dot (
                .clk(clk), .resetn(resetn), .valid(valid), .weights(dot_weights), .activations(activation),
                .ready(dot_ready[p]), .sum(dot_results[p*15 +: 15])
            );
        end
    end endgenerate
    wire memory_request = model_busy ? model_req : link_req;
    wire memory_write = model_busy ? model_wr : link_wr;
    wire [20:0] memory_address = model_busy ? model_addr : link_addr;
    wire [31:0] memory_data = model_busy ? model_data : link_data;
    generate if (SDRAM_FROM_DSP) begin: independent_memory
        // Change SDRAM commands midway between its rising sampling edges.
        wire command_clk = ~divided_dsp_clk;
        reg [7:0] memory_reset_pipe = 0;
        always @(posedge command_clk)
            memory_reset_pipe <= locked && dsp_locked ? {memory_reset_pipe[6:0],1'b1} : 0;
        wire memory_resetn = memory_reset_pipe[7];
        wire sdram_request, sdram_write, sdram_complete, sdram_next_read;
        wire [20:0] sdram_address;
        wire [31:0] sdram_data_in, sdram_data_out;
        tang_sdram_cdc bridge (
            .clk(clk), .resetn(resetn), .sdram_clk(divided_dsp_clk), .sdram_resetn(memory_resetn),
            .request(memory_request), .write(memory_write), .address(memory_address),
            .read_extra(model_busy ? model_read_extra : 5'd0),
            .data_in(memory_data), .complete(complete), .data_out(data_out),
            .sdram_request(sdram_request), .sdram_write(sdram_write), .sdram_next_read(sdram_next_read),
            .sdram_address(sdram_address),
            .sdram_data_in(sdram_data_in), .sdram_complete(sdram_complete), .sdram_data_out(sdram_data_out)
        );
        tang_sdram #(.CLOCK_HZ(DSP_CLOCK_HZ/3), .SEPARATE_CLOCK(1), .KEEP_ROW_OPEN(1)) memory (
            .clk(command_clk), .memory_clk(divided_dsp_clk), .resetn(memory_resetn),
            .request(sdram_request), .write(sdram_write), .read_burst(!sdram_write), .next_read(sdram_next_read),
            .address(sdram_address), .data_in(sdram_data_in), .data_out(sdram_data_out), .complete(sdram_complete),
            .sd_clk(O_sdram_clk), .sd_cke(O_sdram_cke), .sd_cs_n(O_sdram_cs_n),
            .sd_ras_n(O_sdram_ras_n), .sd_cas_n(O_sdram_cas_n), .sd_we_n(O_sdram_wen_n),
            .sd_addr(O_sdram_addr), .sd_bank(O_sdram_ba), .sd_mask(O_sdram_dqm), .sd_dq(IO_sdram_dq)
        );
    end else begin: shared_memory
        tang_sdram #(.CLOCK_HZ(CLOCK_HZ), .CLOCK_DIVIDE(SDRAM_DIVIDER)) memory (
            .clk(clk), .memory_clk(memory_clk), .resetn(resetn),
            .request(memory_request), .write(memory_write), .read_burst(model_busy && model_burst), .next_read(1'b0),
            .address(memory_address), .data_in(memory_data), .data_out(data_out), .complete(complete),
            .sd_clk(O_sdram_clk), .sd_cke(O_sdram_cke), .sd_cs_n(O_sdram_cs_n),
            .sd_ras_n(O_sdram_ras_n), .sd_cas_n(O_sdram_cas_n), .sd_we_n(O_sdram_wen_n),
            .sd_addr(O_sdram_addr), .sd_bank(O_sdram_ba), .sd_mask(O_sdram_dqm), .sd_dq(IO_sdram_dq)
        );
    end endgenerate
endmodule
