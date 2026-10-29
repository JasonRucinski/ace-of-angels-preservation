// Compile/run with zig c++ -target x86-windows-gnu; no game process required.
#include "classic_haze_profiles.h"
#define CHECK(condition) if(!(condition))return __LINE__;
int main(){
 CHECK(select_haze_profile(nullptr,false)==nullptr);
 CHECK(select_haze_profile("unknown_map",false)==nullptr);
 CHECK(select_haze_profile("",true)==nullptr);
 CHECK(haze_name_equal(select_haze_profile("ctf_ARENA",true)->map,"Curt3"));
 CHECK(haze_name_equal(select_haze_profile("CTF_arena",false)->map,"CTF_arena"));
 CHECK(haze_name_equal(select_haze_profile("jrmap292.trn",false)->map,"JRMAP"));
 CHECK(select_haze_profile("CTF_base",false)->count==0);
 for(const auto &p:haze_profiles){CHECK(select_haze_profile(p.map,false)==&p);CHECK(p.count<=2);}
 return 0;
}
