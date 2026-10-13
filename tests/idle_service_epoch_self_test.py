"""Compile the actual idle epoch with spies: modal paths still poll all I/O."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "code/mk61s-M.ino").read_text()
start = source.index("void idle_main_process(void) {")
end = source.index("\n}\n", start) + 3
epoch = source[start:end]

PREAMBLE = r'''
#include "idle_sleep_policy.hpp"
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
#include <vector>
#define TERMINAL 1
#define MK61_PROFILE_SCOPE(point) ((void)0)
#define MK61_IDLE_PROFILE_SCOPE(point) ((void)0)
static std::map<std::string,unsigned> calls;
static std::vector<std::string> order;
static std::vector<unsigned> attempt_depths,deep_depths;
static bool top_level_idle_sleep_permitted,nest_terminal,deep_needed;
static bool busy,alarm;
static u8 idle_main_depth;
static void note(const char* name){++calls[name];order.emplace_back(name);}
static u32 millis(){return 42;}
void idle_main_process();
namespace power_monitor{void poll(u32){note("power");}}
namespace rtc_clock{
struct AlarmEvent{bool missed;};
void poll(){note("rtc");}
bool take_alarm_event(AlarmEvent& out){note("alarm");out.missed=false;return alarm;}
}
namespace usb_mass_storage{void service(){note("msc");}}
namespace usb_screen{
void service(){note("usb");}
bool takeEvent(){note("event");return false;}
}
namespace usb_power{void service(u32){note("usb-power");}}
static void service_terminal(){
  note("terminal");
  if(nest_terminal){nest_terminal=false;idle_main_process();}
}
static bool sound_busy(){note("sound-busy");return busy;}
namespace library_mk61{u32 sound_volume(){return 3;}}
static constexpr unsigned PIN_BUZZER=1;
static void sound(unsigned,unsigned,unsigned,unsigned){note("beep");}
static void sound_poll(){note("sound");}
namespace led{void control(){note("led");}}
namespace disk_activity{void poll(){note("disk");}}
struct Display{void flush(){note("flush");}};
static Display& main_lcd(){static Display display;return display;}
static void idle_signal_poll(){note("signal");}
namespace independent_watchdog{void foreground_epoch(u32){note("watchdog");}}
[[maybe_unused]] static idle_sleep_policy::Conditions idle_sleep_conditions(){
  note("conditions");
  return {top_level_idle_sleep_permitted && idle_main_depth==1,
          true,false,false,false,false,false,false,false,true};
}
namespace idle_sleep{
bool attempt(const idle_sleep_policy::Conditions& value){
  note("attempt");assert(value.foreground_context);
  attempt_depths.push_back(idle_main_depth);return true;
}}
[[maybe_unused]] static idle_sleep_policy::Conditions deep_idle_conditions(
    const idle_sleep_policy::Conditions& value){return value;}
namespace deep_idle{
bool service_needed(){note("deep-needed");return deep_needed;}
bool service(const idle_sleep_policy::Conditions& value,u32){
  note("deep");assert(value.foreground_context==
      (top_level_idle_sleep_permitted && idle_main_depth==1));
  deep_depths.push_back(idle_main_depth);return false;
}}
'''

MAIN = r'''
int main(){
  for(bool top:{false,true})for(unsigned initial_depth:{0U,1U,3U})
    for(bool nested:{false,true})for(bool requested:{false,true})
      for(bool sounding:{false,true})for(bool alarm_ready:{false,true}){
    calls.clear();order.clear();attempt_depths.clear();deep_depths.clear();
    top_level_idle_sleep_permitted=top;idle_main_depth=(u8)initial_depth;
    nest_terminal=nested;deep_needed=requested;busy=sounding;alarm=alarm_ready;
    idle_main_process();assert(idle_main_depth==initial_depth);
    const unsigned epochs=nested?2U:1U;
    const char* services[]={"power","rtc","msc","usb","usb-power","event",
      "terminal","sound-busy","sound","led","disk","flush","signal","watchdog"};
    for(const char* service:services)assert(calls[service]==epochs);
    assert(calls["alarm"]==(sounding?0U:epochs));
    assert(calls["beep"]==(!sounding && alarm_ready?epochs:0U));
    const unsigned attempts=MK61_IDLE_WFI_SUPPORTED && top && initial_depth==0?1U:0U;
    assert(calls["attempt"]==attempts);
    for(unsigned depth:attempt_depths)assert(depth==1);
    const unsigned deep=MK61_IDLE_WFI_SUPPORTED && MK61_DEEP_IDLE_SUPPORTED && requested?epochs:0U;
    assert(calls["deep"]==deep && calls["conditions"]==deep+attempts);
    // Flatten nested epochs: the non-modal sequence is still exactly ordered.
    if(!nested){
      std::vector<std::string> actual;
      for(const auto& item:order)
        for(const char* service:services)if(item==service)actual.push_back(item);
      assert(actual==std::vector<std::string>(std::begin(services),std::end(services)));
    }
  }
  std::puts("idle epoch: modal/nested I/O order, WFI ownership, deep service, alarm/watchdog PASS");
}
'''

with tempfile.TemporaryDirectory(prefix="mk61-idle-epoch-") as temp:
    work = Path(temp)
    cpp = work / "idle_epoch.cpp"
    cpp.write_text(PREAMBLE + epoch + MAIN)
    sanitizers = (["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                  if os.environ.get("MK61_TEST_SANITIZERS") == "1" else [])
    for wfi, deep in ((0, 0), (1, 0), (1, 1)):
        output = work / f"epoch-{wfi}-{deep}"
        subprocess.run(["clang++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        *sanitizers,
                        f"-DMK61_IDLE_WFI_SUPPORTED={wfi}",
                        f"-DMK61_DEEP_IDLE_SUPPORTED={deep}", "-I"+str(ROOT/"code"),
                        str(cpp), "-o", str(output)], check=True)
        subprocess.run([str(output)], check=True)
