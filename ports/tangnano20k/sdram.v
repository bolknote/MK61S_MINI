// GW2AR-18 internal 4-bank × 2048-row × 256-column × 32-bit SDRAM.
// Eight-word SDR read bursts fill a one-line cache. Writes are single-word.
module tang_sdram #(
    parameter CLOCK_HZ = 54000000
) (
    input wire clk, memory_clk, resetn,
    input wire request, write,
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
    localparam POWER_WAIT = CLOCK_HZ / 4000;
    localparam REFRESH_SPACING = (CLOCK_HZ / 1000000) * 12;
    localparam [3:0] COLUMN_DELAY = (CLOCK_HZ + 49999999) / 50000000;
    localparam [3:0] REFRESH_DELAY = ((CLOCK_HZ / 1000000) * 72 + 999) / 1000;
    localparam [3:0] FIRST_READ = COLUMN_DELAY + 2;
    localparam FIRST_REFRESH = POWER_WAIT + 2;
    localparam SECOND_REFRESH = FIRST_REFRESH + REFRESH_DELAY;
    localparam SET_MODE = SECOND_REFRESH + REFRESH_DELAY;
    localparam INIT = 0, IDLE = 1, ACCESS = 2, REFRESHING = 3, COMPLETE = 4;
    reg [2:0] command, state;
    reg [14:0] startup;
    reg [10:0] refresh_due;
    reg [3:0] cycles;
    reg [7:0] column;
    reg writing, output_enable;
    reg [31:0] drive_data;
    reg [31:0] line [0:7];
    reg [17:0] line_address;
    reg line_valid;

    assign sd_clk = memory_clk;
    assign sd_cke = 1'b1;
    assign sd_cs_n = 1'b0;
    assign {sd_ras_n, sd_cas_n, sd_we_n} = command;
    assign sd_mask = 4'b0000;
    assign sd_dq = output_enable ? drive_data : 32'bz;

    always @(posedge clk) begin
        command <= NOP;
        complete <= 0;
        output_enable <= 0;
        if (!resetn) begin
            state <= INIT;
            startup <= 0;
            sd_addr <= 0;
            sd_bank <= 0;
            refresh_due <= REFRESH_SPACING;
            line_valid <= 0;
        end else if (state == INIT) begin
            startup <= startup + 1'b1;
            case (startup)
                POWER_WAIT: begin command <= PRECHARGE; sd_addr[10] <= 1; end
                FIRST_REFRESH, SECOND_REFRESH: command <= REFRESH;
                SET_MODE: begin command <= MODE; sd_addr <= 11'h223; end
                SET_MODE + 3: state <= IDLE;
            endcase
        end else begin
            if (refresh_due != 0) refresh_due <= refresh_due - 1'b1;
            case (state)
                IDLE: begin
                    cycles <= 1;
                    if (refresh_due == 0) begin
                        command <= REFRESH;
                        refresh_due <= REFRESH_SPACING;
                        state <= REFRESHING;
                    end else if (request) begin
                        if (!write && line_valid && line_address == address[20:3]) begin
                            data_out <= line[address[2:0]];
                            complete <= 1;
                            state <= COMPLETE;
                        end else begin
                            command <= ACTIVATE;
                            sd_bank <= address[20:19];
                            sd_addr <= address[18:8];
                            column <= address[7:0];
                            writing <= write;
                            drive_data <= data_in;
                            if (!write) begin line_address <= address[20:3]; line_valid <= 0; end
                            else if (line_address == address[20:3]) line_valid <= 0;
                            state <= ACCESS;
                        end
                    end
                end
                ACCESS: begin
                    cycles <= cycles + 1'b1;
                    if (cycles == COLUMN_DELAY) begin
                        command <= writing ? WRITE : READ;
                        sd_addr <= {1'b1, 2'b00, column[7:3], writing ? column[2:0] : 3'b0};
                        output_enable <= writing;
                    end
                    // CAS latency 2 and the selected clock phase put the first
                    // word on the fabric side two cycles after READ.
                    if (!writing && cycles >= FIRST_READ) line[cycles - FIRST_READ] <= sd_dq;
                    if (writing ? cycles == COLUMN_DELAY + 4'd3 : cycles == FIRST_READ + 4'd7) begin
                        if (!writing) begin
                            data_out <= column[2:0] == 7 ? sd_dq : line[column[2:0]];
                            line_valid <= 1;
                        end
                        complete <= 1;
                        state <= COMPLETE;
                    end
                end
                COMPLETE: state <= IDLE;
                REFRESHING: begin
                    cycles <= cycles + 1'b1;
                    if (cycles == REFRESH_DELAY) state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
