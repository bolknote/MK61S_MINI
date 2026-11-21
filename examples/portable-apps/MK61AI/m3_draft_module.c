#include "stm3_module.h"

enum { HISTORY_LIMIT=118, HEADER=4, REPLY=8 };
static unsigned token_at(const uint8_t *tokens, unsigned i) {
    return tokens[2*i] | (unsigned)tokens[2*i+1] << 8;
}
uint32_t module_entry(uint32_t op, const stm3_api *api, stm3_job *job) {
    if (op==STM3_CANCEL || op==STM3_FINI) return STM3_DONE;
    if (op!=STM3_INIT || !api || api->abi!=STM3_ABI || api->size<sizeof(*api) ||
        !job || !job->input || !job->output || job->input_bytes<HEADER || job->output_capacity<REPLY)
        return STM3_INVALID;
    const uint8_t *in=job->input;
    const unsigned count=in[2], generated=in[3];
    if (in[0]!='K' || in[1]!='D' || count>HISTORY_LIMIT || generated>count ||
        job->input_bytes!=HEADER+2*count)
        return STM3_INVALID;
    const uint8_t *tokens=in+HEADER;
    unsigned guess=65535, confidence=0, source=0;
    if (count>=2) {
        const unsigned last=token_at(tokens,count-1);
        unsigned run=1;
        while (run<generated && token_at(tokens,count-1-run)==last) ++run;
        if (run>=2) {
            guess=last;
            confidence=run>=3 ? 240 : 218;
            source=1;
        } else {
            unsigned length=1, choice=0, samples=0, votes=0;
            for (unsigned at=2; at<count; ++at) {
                unsigned m=0;
                while (m<6 && m<at && token_at(tokens,count-1-m)==token_at(tokens,at-1-m)) ++m;
                if (m<2 || m<length) continue;
                const unsigned next=token_at(tokens,at);
                if (m>length) {
                    length=m; choice=next; samples=votes=1;
                } else {
                    ++samples;
                    if (next==choice) ++votes;
                }
            }
            if (votes) {
                guess=choice;
                confidence=255*votes/(samples+1);
                source=2;
            }
        }
    }
    uint8_t *out=job->output;
    out[0]='K'; out[1]='D'; out[2]=(uint8_t)guess; out[3]=(uint8_t)(guess>>8);
    out[4]=(uint8_t)confidence; out[5]=(uint8_t)source; out[6]=out[7]=0;
    job->output_bytes=REPLY;
    job->progress=1;
    return STM3_DONE;
}
