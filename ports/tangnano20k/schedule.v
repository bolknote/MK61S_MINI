// A sequencer for the RV32I instructions used by schedule.S. The ROM uses
// x0-x7 and four fixed, word-aligned mailbox addresses. Execution stops on
// the result store. There is no external program or memory interface.
module tang_schedule (
    input wire clk, resetn, start,
    input wire [15:0] single_cost, pair_cost,
    input wire [7:0] confidence,
    output reg done, pair
);
    localparam IDLE=0, FETCH=1, LEFT=2, RIGHT=3, EXECUTE=4;
    reg [2:0] state;
    reg [4:0] pc;
    reg [31:0] rom [0:31];
    initial $readmemh("schedule.hex",rom);
    reg [31:0] instruction;
    reg [31:0] registers [1:7];
    reg [31:0] left, right;
    wire [2:0] address = state == LEFT ? instruction[17:15] : instruction[22:20];
    wire [31:0] value = address == 0 ? 32'd0 : registers[address];
    wire [6:0] opcode = instruction[6:0];
    wire [2:0] funct = instruction[14:12];
    wire branch = opcode == 7'h63;
    wire subtract = branch || (opcode == 7'h33 && instruction[30]);
    wire [31:0] immediate = {{20{instruction[31]}},instruction[31:20]};
    wire [31:0] operand = opcode == 7'h13 ? immediate : right;
    wire [32:0] addition = {1'b0,left} + {1'b0,(subtract ? ~operand : operand)} + subtract;
    wire taken = funct == 3'h7 ? addition[32] :
                 funct == 3'h1 ? left != right : left == right;
    wire [4:0] target = pc + (branch && taken ? {instruction[26:25],instruction[11:9]} : 5'd1);
    reg [31:0] result;

    always @* begin
        result = addition[31:0];
        if (opcode == 7'h03) begin
            case (instruction[23:22])
                0: result = {16'b0,single_cost};
                1: result = {16'b0,pair_cost};
                2: result = {24'b0,confidence};
                default: result = 0;
            endcase
        end else if (opcode == 7'h13) begin
            case (funct)
                1: result = instruction[23] ? {left[23:0],8'd0} : {left[30:0],1'b0};
                5: result = {1'b0,left[31:1]};
                7: result = {31'b0,left[0]};
                default: result = addition[31:0];
            endcase
        end
    end

    always @(posedge clk) begin
        done <= 0;
        if (!resetn) begin
            state <= IDLE;
            pair <= 0;
        end else case (state)
            IDLE: if (start) begin pc <= 0; pair <= 0; state <= FETCH; end
            FETCH: begin instruction <= rom[pc]; state <= LEFT; end
            LEFT: begin left <= value; state <= RIGHT; end
            RIGHT: begin right <= value; state <= EXECUTE; end
            EXECUTE: begin
                if (opcode == 7'h23) begin
                    pair <= right == 2;
                    done <= 1;
                    state <= IDLE;
                end else begin
                    if (!branch && instruction[9:7] != 0)
                        registers[instruction[9:7]] <= result;
                    pc <= target;
                    state <= FETCH;
                end
            end
            default: state <= IDLE;
        endcase
    end
endmodule
