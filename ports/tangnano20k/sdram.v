// GW2AR-18 internal 4-bank × 2048-row × 256-column × 32-bit SDRAM.
// Eight-word SDR read bursts fill a one-line cache. Writes are single-word.
module tang_sdram #(
    parameter CLOCK_HZ = 54000000,
    parameter CLOCK_DIVIDE = 1,
    parameter SEPARATE_CLOCK = 0,
    parameter KEEP_ROW_OPEN = 0
) (
    input wire clk, memory_clk, resetn,
    input wire request, write, read_burst, next_read,
    input wire [20:0] address,
    input wire [31:0] data_in,
    output reg [31:0] data_out,
    output reg complete,
    output wire sd_clk, sd_cke, sd_cs_n,
    output wire sd_ras_n, sd_cas_n, sd_we_n,
    output reg [10:0] sd_addr,
    output reg [1:0] sd_bank,
    output wire [3:0] sd_mask,
    inout wire [31:0] sd_dq
);
    localparam [2:0] MODE = 0, REFRESH = 1, PRECHARGE = 2, ACTIVATE = 3,
                     WRITE = 4, READ = 5, NOP = 7;
    localparam SDRAM_HZ = CLOCK_HZ / CLOCK_DIVIDE;
    localparam POWER_WAIT = SDRAM_HZ / 4000;
    localparam REFRESH_SPACING = (SDRAM_HZ / 1000000) * 12;
    localparam [3:0] COLUMN_DELAY = (SDRAM_HZ + 49999999) / 50000000;
    localparam [3:0] REFRESH_DELAY = ((SDRAM_HZ / 1000000) * 72 + 999) / 1000;
    localparam [3:0] FIRST_READ = COLUMN_DELAY + (CLOCK_DIVIDE == 3 ? 2 : 3);
    localparam FIRST_REFRESH = POWER_WAIT + 2;
    localparam SECOND_REFRESH = FIRST_REFRESH + REFRESH_DELAY;
    localparam SET_MODE = SECOND_REFRESH + REFRESH_DELAY;
    localparam INIT = 0, IDLE = 1, ACCESS = 2, REFRESHING = 3, COMPLETE = 4, LOOKUP = 5, PRECHARGING = 6;
    reg [2:0] command, state;
    reg [14:0] startup;
    reg [10:0] refresh_due;
    reg [3:0] cycles;
    reg [7:0] column;
    reg [20:0] pending_address;
    reg writing, streaming, output_enable;
    reg [31:0] drive_data, sampled_data;
    reg [31:0] line [0:7];
    reg [17:0] line_address;
    reg line_valid;
    reg row_open, precharge_for_refresh;
    reg [12:0] open_row;
    reg read_chained;
    wire [4:0] next_column = column[7:3] + 1'b1;
    wire step_memory;
    wire [31:0] read_port = CLOCK_DIVIDE == 3 ? sd_dq : sampled_data;

    generate if (CLOCK_DIVIDE == 1) begin: from_pll
        assign sd_clk = memory_clk;
        assign step_memory = 1'b1;
    end else if (CLOCK_DIVIDE == 2) begin: divide_by_two
        reg divided_clock;
        always @(posedge clk) divided_clock <= resetn && !divided_clock;
        assign sd_clk = divided_clock;
        assign step_memory = divided_clock;
    end else begin: divide_by_three
        reg [1:0] phase;
        reg divided_clock;
        always @(posedge clk) begin
            if (!resetn || phase == 2) begin phase <= 0; divided_clock <= 0; end
            else begin phase <= phase + 1'b1; divided_clock <= 1; end
        end
        assign sd_clk = divided_clock;
        assign step_memory = phase == 2;
    end endgenerate
    assign sd_cke = 1'b1;
    assign sd_cs_n = 1'b0;
    assign {sd_ras_n, sd_cas_n, sd_we_n} = command;
    assign sd_mask = 4'b0000;
    assign sd_dq = output_enable ? drive_data : 32'bz;

    // The independent controller changes commands on SDRAM's falling edge
    // and consumes the word sampled on the preceding rising edge.
    generate if (SEPARATE_CLOCK) begin: sample_sdram
        always @(posedge memory_clk) sampled_data <= sd_dq;
    end else begin: sample_fabric
        always @(posedge clk) sampled_data <= sd_dq;
    end endgenerate

    always @(posedge clk) begin
        // Change divided-clock commands on the falling edge. The line cache
        // still serves hits at the full fabric clock.
        if (step_memory) begin
            command <= NOP;
            output_enable <= 0;
        end
        complete <= 0;
        if (!resetn) begin
            command <= NOP;
            output_enable <= 0;
            state <= INIT;
            startup <= 0;
            sd_addr <= 0;
            sd_bank <= 0;
            refresh_due <= REFRESH_SPACING;
            line_valid <= 0;
            row_open <= 0;
            read_chained <= 0;
        end else if (state == INIT) begin
            if (step_memory) begin
                startup <= startup + 1'b1;
                case (startup)
                    POWER_WAIT: begin command <= PRECHARGE; sd_addr[10] <= 1; end
                    FIRST_REFRESH, SECOND_REFRESH: command <= REFRESH;
                    SET_MODE: begin command <= MODE; sd_addr <= 11'h223; end
                    SET_MODE + 3: state <= IDLE;
                endcase
            end
        end else begin
            if (step_memory && refresh_due != 0) refresh_due <= refresh_due - 1'b1;
            case (state)
                IDLE: begin
                    cycles <= 1;
                    if (refresh_due == 0) begin
                        if (step_memory) begin
                            if (KEEP_ROW_OPEN && row_open) begin
                                command <= PRECHARGE;
                                sd_addr <= 11'h400;
                                row_open <= 0;
                                precharge_for_refresh <= 1;
                                state <= PRECHARGING;
                            end else begin
                                command <= REFRESH;
                                refresh_due <= REFRESH_SPACING;
                                state <= REFRESHING;
                            end
                        end
                    end else if (request) begin
                        pending_address <= address;
                        column <= address[7:0];
                        writing <= write;
                        streaming <= !write && (SEPARATE_CLOCK || (read_burst && address[2:0] == 0));
                        drive_data <= data_in;
                        state <= LOOKUP;
                    end
                end
                LOOKUP: begin
                    if (!SEPARATE_CLOCK && !writing && !streaming && line_valid &&
                        line_address == pending_address[20:3]) begin
                        data_out <= line[column[2:0]];
                        complete <= 1;
                        state <= COMPLETE;
                    end else if (step_memory) begin
                        if (KEEP_ROW_OPEN && row_open && open_row != pending_address[20:8]) begin
                            command <= PRECHARGE;
                            sd_addr <= 11'h400;
                            row_open <= 0;
                            precharge_for_refresh <= 0;
                            state <= PRECHARGING;
                        end else begin
                            if (KEEP_ROW_OPEN && row_open) cycles <= COLUMN_DELAY;
                            else begin
                                command <= ACTIVATE;
                                sd_bank <= pending_address[20:19];
                                sd_addr <= pending_address[18:8];
                                row_open <= 1;
                                open_row <= pending_address[20:8];
                            end
                            output_enable <= writing;
                            if (!SEPARATE_CLOCK) begin
                                if (!writing) begin line_address <= pending_address[20:3]; line_valid <= 0; end
                                else if (line_address == pending_address[20:3]) line_valid <= 0;
                            end
                            state <= ACCESS;
                        end
                    end
                end
                ACCESS: if (step_memory) begin
                    cycles <= cycles + 1'b1;
                    output_enable <= writing && cycles <= COLUMN_DELAY + 4'd1;
                    if (cycles == COLUMN_DELAY) begin
                        command <= writing ? WRITE : READ;
                        sd_addr <= {KEEP_ROW_OPEN ? 1'b0 : 1'b1,
                                    2'b00, column[7:3], writing ? column[2:0] : 3'b0};
                    end
                    // Start the next BL8 before the last beats reach the
                    // reader. The bridge advances its address on beat eight.
                    if (SEPARATE_CLOCK && KEEP_ROW_OPEN && !writing && next_read &&
                        column[7:3] != 31 && cycles == COLUMN_DELAY + 4'd8) begin
                        command <= READ;
                        sd_addr <= {3'b0,next_column,3'b0};
                        read_chained <= 1;
                    end
                    if (!writing && cycles >= FIRST_READ) begin
                        if (!SEPARATE_CLOCK) line[cycles - FIRST_READ] <= read_port;
                        // An aligned streaming caller consumes each beat as
                        // it arrives. Word reads still return once per request.
                        if (streaming) begin
                            data_out <= read_port;
                            complete <= 1;
                        end
                    end
                    if (writing ? cycles == COLUMN_DELAY + 4'd3 : cycles == FIRST_READ + 4'd7) begin
                        if (!SEPARATE_CLOCK && !writing) begin
                            if (!streaming)
                                data_out <= column[2:0] == 7 ? read_port : line[column[2:0]];
                            line_valid <= 1;
                        end
                        complete <= 1;
                        if (SEPARATE_CLOCK && read_chained) begin
                            read_chained <= 0;
                            column <= {next_column,3'b0};
                            cycles <= FIRST_READ;
                        end else state <= COMPLETE;
                    end
                end
                COMPLETE: state <= IDLE;
                PRECHARGING: if (step_memory) begin
                    if (cycles == COLUMN_DELAY) begin
                        cycles <= 1;
                        state <= precharge_for_refresh ? IDLE : LOOKUP;
                    end else cycles <= cycles + 1'b1;
                end
                REFRESHING: if (step_memory) begin
                    cycles <= cycles + 1'b1;
                    if (cycles == REFRESH_DELAY) state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
