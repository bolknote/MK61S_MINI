/* Historical actual Keyboard::poll; preserves the stale-selection bug witness. */
bool Keyboard::poll(KeyEvent& event) {
    const u64 now = time_us_64();
    if(io_phase_) {
        if((io_phase_==4 || io_phase_==6 || io_phase_==8) && pending_ && now>=due_) {
            if(io_worker::request_i2c(true,nullptr,2)) pending_=false;
            return false;
        }
        if((io_phase_==4 || io_phase_==6 || io_phase_==8) && pending_) return false;
        int count;u8 response[2]{};
        if(!io_worker::take_i2c(count,response)) return false;
        const u8 phase=io_phase_;io_phase_=0;
        if(phase==1) {
            if(count==1) { pending_=true;due_=now+16000; }
            else { online_=false;battery_.power_status=0;++errors_;due_=now+100000; }
            return false;
        }
        if(phase==3 || phase==5 || phase==7) {
            if(count==1) { pending_=true;io_phase_=phase+1;due_=now+16000; }
            else { ++battery_errors_;if(phase==3) battery_.clear_reading();else battery_.clear_power(); }
            return false;
        }
        if(phase==4) {
            pending_=false;
            if(count!=2 || !battery_.decode(response[0],response[1])) { ++battery_errors_;battery_.clear_reading(); }
            battery_due_=now+20000000;return false;
        }
        if(phase==6) {
            pending_=false;
            if(count!=2) { ++battery_errors_;battery_.clear_power(); }
            else battery_.decode_power(response[0],response[1]); // Old BIOS: unsupported, not an I2C error.
            power_due_=now+(battery_.power_supported()?1000000:20000000);return false;
        }
        if(phase==8) {
            pending_=false;
            // Older Southbridge echoes its previous payload for an unknown
            // register. Seed that payload with a version byte outside the
            // power tag range before discovering the optional register.
            if(count==2 && response[0]<=1 && (response[1]&BIOS_POWER_TAG_MASK)!=BIOS_POWER_TAG) {
                const u8 reg=BIOS_POWER_REG;
                if(io_worker::request_i2c(false,&reg,1)) io_phase_=5;
                else power_due_=now;
            } else { if(count!=2) ++battery_errors_;battery_.clear_power(); }
            return false;
        }
        pending_=false;online_=count==2;
        if(!online_) { battery_.power_status=0;++errors_;due_=now+100000;return false; }
        event={response[0],response[1]};
        if(idle_ && !event.state) due_=now+64000;
        return event.state!=0;
    }
    if(!idle_ && online_ && !pending_ && now>=battery_due_) {
        const u8 reg=0x0B;
        if(io_worker::request_i2c(false,&reg,1)) { io_phase_=3;battery_due_=now+20000000; }
        return false;
    }
    if(!idle_ && online_ && !pending_ && now>=power_due_) {
        const bool known=battery_.power_supported();const u8 reg=known?BIOS_POWER_REG:0x01;
        if(io_worker::request_i2c(false,&reg,1)) { io_phase_=known?5:7;power_due_=now+20000000; }
        return false;
    }
    if(now < due_) return false;
    diagnostics::Scope measure(diagnostics::Point::KEYBOARD);
    if(!pending_) {
        const u8 reg = 0x09;
        if(io_worker::request_i2c(false,&reg,1)) io_phase_=1;
        return false;
    }
    if(io_worker::request_i2c(true,nullptr,2)) io_phase_=2;
    return false;
}
