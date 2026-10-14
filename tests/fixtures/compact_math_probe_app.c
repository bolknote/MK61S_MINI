/* Diagnostic user APP: exercise resident binary64 services against independent
 * vectors, then time identical 1024-call batches. It changes only reserved
 * test files; the host runner installs/removes them and verifies preservation.
 * Build with tools/build_portable_app.py --name MATHCHK --source this-file.
 */
#include "mk61_app.h"
#include <stdint.h>

#define OPERATIONS 11U
#define ROUNDS 9U
#define SAMPLES 1024U
#define SIGN UINT64_C(0x8000000000000000)
#define INF UINT64_C(0x7ff0000000000000)

typedef union { double number; uint64_t bits; } binary64;
typedef struct { uint32_t operation, reserved; uint64_t a,b,expected; } vector;
typedef struct {
  uint32_t magic,version,samples,rounds,cases,failures;
  uint64_t worst[OPERATIONS];
  uint32_t microseconds[OPERATIONS][ROUNDS];
  uint32_t first_index,first_operation,padding;
  uint64_t first_expected,first_actual,checksum;
} result;
static result report;
static uint64_t ordered(uint64_t x) { return x&SIGN?~x:x|SIGN; }
int main(void) {
  const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_MATH);
  if (!s || !s->math || !mk61_api->file_read) return MK61_APP_RUNTIME_ERROR;
  report.magic=UINT32_C(0x54414d51);report.version=1;report.samples=SAMPLES;report.rounds=ROUNDS;
  uint32_t total=0;
  for (uint32_t part=0;!total || report.cases<total;++part) {
    if (part>=32) return MK61_APP_INVALID_FILE;
    char name[]="/MATH00.bin";name[5]=(char)('0'+part/10);name[6]=(char)('0'+part%10);
    mk61_service_file file={0};
    if (s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
                (uint32_t)(uintptr_t)name,&file)!=0) return MK61_APP_IO_ERROR;
    uint32_t header[4];
    if (mk61_api->file_read(file.id,0,(uint8_t*)header,sizeof(header))!=sizeof(header) ||
        header[0]!=UINT32_C(0x5641544d) || !header[1] || header[1]>127 ||
        header[2]!=report.cases || header[3]<1800 || header[3]>4064 ||
        (total && header[3]!=total) ||
        mk61_api->file_size(file.id)!=16+header[1]*sizeof(vector)) return MK61_APP_INVALID_FILE;
    total=header[3];
    for (uint32_t i=0;i<header[1];++i) {
    vector v;
    if (mk61_api->file_read(file.id,16+i*sizeof(v),(uint8_t*)&v,sizeof(v))!=sizeof(v) ||
        v.operation>=OPERATIONS || v.reserved) return MK61_APP_INVALID_FILE;
    binary64 a={.bits=v.a},b={.bits=v.b},actual={.number=s->math(v.operation,a.number,b.number)};
    const uint64_t magnitude=v.expected&~SIGN,got=actual.bits&~SIGN;
    uint32_t valid;
    if (magnitude>INF) valid=got>INF;
    else if (!magnitude || magnitude==INF) valid=actual.bits==v.expected;
    else {
      const uint64_t x=ordered(actual.bits),y=ordered(v.expected),ulp=x>=y?x-y:y-x;
      if (ulp>report.worst[v.operation]) report.worst[v.operation]=ulp;
      valid=got<INF && ulp<=(v.operation==MK61_SERVICE_SQRT?0U:4U);
    }
    if (!valid) {
      if (!report.failures) {
        report.first_index=report.cases;report.first_operation=v.operation;
        report.first_expected=v.expected;report.first_actual=actual.bits;
      }
      ++report.failures;
    }
    ++report.cases;report.checksum^=actual.bits;
    if (!(i&31)) mk61_api->service();
    }
  }
  for (uint32_t operation=0;operation<OPERATIONS;++operation) {
    const double input=operation<=MK61_SERVICE_ATAN?0.7:1.3;
    for (uint32_t r=0;r<ROUNDS;++r) {
      mk61_api->service();
      const uint32_t started=s->call(MK61_SERVICE_MICROS,0,0,0,0);
      uint64_t checksum=0;
      for (uint32_t i=0;i<SAMPLES;++i) {
        const binary64 value={.number=s->math(operation,input,0.7)};
        checksum^=value.bits;
      }
      report.microseconds[operation][r]=s->call(MK61_SERVICE_MICROS,0,0,0,0)-started;
      report.checksum^=checksum;
    }
  }
  mk61_service_write out={"MATHOUT",(const uint8_t*)&report,sizeof(report),MK61_SERVICE_INVALID_ID};
  return s->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,
                 MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
