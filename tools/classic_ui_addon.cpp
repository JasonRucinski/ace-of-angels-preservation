// MIT licensed. Optional offline ReShade 6.8.0 add-on for the pinned AOA 2.9.2 client.
// Run world effects after 43CCF0 and before the HUD/target-preview draw calls.
#include <reshade.hpp>
#include <windows.h>
#include <d3d11_1.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <algorithm>

static reshade::api::effect_runtime *runtime=nullptr;
static bool installed=false, in_effect=false, applied=false;
static unsigned frames=0, calls=0, capture_step=0;
static bool capture_enabled=false;
static unsigned engine_capture_step=0;
static bool fleet_capture=false;
static unsigned haze_capture_step=0;
static bool haze_camera_valid=false,haze_seeded=false;
static float haze_origin[3],haze_right[3],haze_up[3],haze_forward[3],haze_projection[4],haze_centers[2][3];
static unsigned char patch[6];
static ID3D11ShaderResourceView *world_depth=nullptr;
static const unsigned char original[6]={0x8b,0x8e,0x98,0x01,0x00,0x00};
static void log(const char *s){FILE*f=fopen("classic-ui.log","a");if(f){fprintf(f,"%s\n",s);fclose(f);}}
// Only read native state. No physics, asset, or input changes.
static constexpr unsigned max_engines=64, pilot_slots=50, object_slots=1000, max_ships=pilot_slots+object_slots;
static float engine_start[max_engines][4]={}, engine_end[max_engines][4]={};
static unsigned engine_count=0, player_engine_count=0;
struct MotionState {uintptr_t node=0;uint32_t tag=0;float position[3]={},power=0;DWORD time=0;};
static MotionState ship_motion[max_ships];
static bool read_native(uintptr_t address,void *out,size_t count){
 SIZE_T got=0;return address && ReadProcessMemory(GetCurrentProcess(),(void*)address,out,count,&got) && got==count;
}
static uintptr_t pointer(uintptr_t address){uintptr_t p=0;read_native(address,&p,sizeof(p));return p;}
static void project_point(const float *p,const float *view,const float *proj,float *out,float radius=4.5f){
 float q[4]={},c[4]={};
 for(int j=0;j<4;++j)q[j]=p[0]*view[j]+p[1]*view[4+j]+p[2]*view[8+j]+view[12+j];
 for(int j=0;j<4;++j)for(int k=0;k<4;++k)c[j]+=q[k]*proj[k*4+j];
 if(c[3]<=1 || !std::isfinite(c[3]) || !std::isfinite(c[0]) || !std::isfinite(c[1]) || c[2]<0 || c[2]>c[3]){out[3]=0;return;}
 out[0]=0.5f+0.5f*c[0]/c[3];out[1]=0.5f-0.5f*c[1]/c[3];out[2]=c[2]/c[3];out[3]=fabsf(proj[5]*radius/c[3]);
}
static bool exhaust_name(const char *name){
 const char *suffix=nullptr;
 if(_strnicmp(name,"trail",5)==0)suffix=name+5;
 else if(_strnicmp(name,"tail",4)==0)suffix=name+4;
 if(suffix && *suffix=='_')++suffix;
 if(!suffix || !*suffix)return false;
 for(;*suffix;++suffix)if(*suffix<'0' || *suffix>'9')return false;
 return true;
}
// Experimental retrofit outlets for models without native exhaust anchors.
// Positions are in original Gob coordinates, behind inspected rear hull surfaces.
// These are new art placements, not recovered original engine hardpoints.
struct ExhaustProfile {const char *model;bool capital;float radius,length;unsigned count;float points[4][3];};
static const ExhaustProfile exhaust_profiles[]={
 {"Eagle",false,3.5f,40,2,{{-18,8,-67},{18,8,-67}}},
 {"Janha Vari",false,2.5f,35,1,{{0,2,-80}}},
 {"Vermok",false,3.0f,40,1,{{-10,-2,-49}}},
 {"ZCS",true,100,1500,1,{{-58.6f,-65.9f,-4520}}},
 {"Tug1",true,65,600,2,{{-210,-35,-1660},{210,-35,-1660}}},
 {"ZCVS",true,150,1800,2,{{-1118,-575,-5740},{1118,-575,-5740}}},
 {"ztugcargo",true,45,500,2,{{-242,-96,-1190},{242,-96,-1190}}},
};
static const ExhaustProfile *exhaust_profile(uintptr_t node){
 char model[64]={};if(!read_native(pointer(node+0x20),model,63))return nullptr;
 for(const auto &profile:exhaust_profiles)if(_stricmp(model,profile.model)==0)return &profile;
 return nullptr;
}
static void update_engines(){
 haze_camera_valid=false;
 engine_count=player_engine_count=0;
 memset(engine_start,0,sizeof(engine_start));memset(engine_end,0,sizeof(engine_end));
 uintptr_t app=pointer(0x5e6e58),world=pointer(0x5e7728),player=pointer(world+0xd3448);
 if(!app || !world || pointer(app+0x20)!=0x44afd0){haze_seeded=false;return;}
 uintptr_t gfx=pointer(app+0x138);auto device=(void*)pointer(gfx+0x188);
 if(!device)return;
 // IDirect3DDevice7::GetTransform is vtable slot 12 (legacy d3d.h).
 using GetTransform=HRESULT(WINAPI*)(void*,DWORD,float*);
 auto get_transform=(GetTransform)((void**)*(void***)device)[12];
 float view[16],proj[16];
 if(FAILED(get_transform(device,2,view)) || FAILED(get_transform(device,3,proj)))return;
 // Reconstruct the native camera from its rigid world-to-view transform.
 // Pockets are placed once on flight entry; they never follow the camera.
 for(float v:view)if(!std::isfinite(v))return;
 for(float v:proj)if(!std::isfinite(v))return;
 if(fabsf(proj[0])<0.00001f || fabsf(proj[5])<0.00001f || fabsf(proj[14])<0.00001f)return;
 for(int j=0;j<3;++j){
  haze_right[j]=view[j*4];haze_up[j]=view[j*4+1];haze_forward[j]=view[j*4+2];
  haze_origin[j]=-view[12]*haze_right[j]-view[13]*haze_up[j]-view[14]*haze_forward[j];
 }
 haze_projection[0]=1/proj[0];haze_projection[1]=1/proj[5];
 haze_projection[2]=proj[10];haze_projection[3]=proj[14];
 if(!haze_seeded){
  for(int j=0;j<3;++j){
   haze_centers[0][j]=haze_origin[j]-6500*haze_right[j]-2000*haze_up[j]+18000*haze_forward[j];
   haze_centers[1][j]=haze_origin[j]+26000*haze_right[j]+7000*haze_up[j]+60000*haze_forward[j];
  }
  haze_seeded=true;
 }
 haze_camera_valid=true;
 if(haze_capture_step){
  char line[240];sprintf(line,"haze camera=%.1f,%.1f,%.1f projection=%.6f,%.6f,%.6f,%.6f",haze_origin[0],haze_origin[1],haze_origin[2],haze_projection[0],haze_projection[1],haze_projection[2],haze_projection[3]);log(line);
  sprintf(line,"haze centers=%.1f,%.1f,%.1f / %.1f,%.1f,%.1f",haze_centers[0][0],haze_centers[0][1],haze_centers[0][2],haze_centers[1][0],haze_centers[1][1],haze_centers[1][2]);log(line);
 }
 // Pilot and dynamic-object tables are read in bounded copies. Only explicitly
 // profiled capital models are admitted from the latter; HUD previews stay out.
 static unsigned char pilots[pilot_slots*0x3b0],objects[object_slots*0x360];
 if(!read_native(world+0xd32ac,pilots,sizeof(pilots)) || !read_native(world+0x4c,objects,sizeof(objects)))return;
 struct Candidate {uintptr_t node;unsigned slot;float matrix[16],distance;bool own;const ExhaustProfile *profile;};
 static Candidate candidates[max_ships];unsigned total=0;DWORD now=GetTickCount();
 for(unsigned slot=0;slot<max_ships;++slot){
  bool dynamic=slot>=pilot_slots;
  auto record=dynamic?objects+(slot-pilot_slots)*0x360:pilots+slot*0x3b0;uintptr_t node=0;uint32_t tag=0;
  memcpy(&node,record+0x19c,4);memcpy(&tag,record+0x178,4);
  auto &motion=ship_motion[slot];
  if(!record[0x243] || !node){motion={};continue;}
  const auto *profile=exhaust_profile(node);
  if(dynamic && (!profile || !profile->capital)){motion={};continue;}
  float m[16];if(!read_native(node+0x7c,m,sizeof(m))){motion={};continue;}
  bool finite=true;for(float value:m)finite=finite && std::isfinite(value);
  if(!finite){motion={};continue;}
  float dt=(now-motion.time)*0.001f;
  if(motion.node==node && motion.tag==tag && dt>0 && dt<0.25f){
   float speed=0;for(int j=0;j<3;++j)speed+=(m[12+j]-motion.position[j])*m[8+j]/dt;
   motion.power+=(fminf(fabsf(speed)/250.0f,1.0f)-motion.power)*fminf(dt*4.0f,1.0f);
  }else motion.power=0;
  motion.node=node;motion.tag=tag;motion.time=now;memcpy(motion.position,m+12,12);
  bool own=node==player;unsigned char flags[2]={};read_native(node+0x150,flags,2);
  // Native clock can advance inside a frame. Keep own-ship chase data only while fresh.
  if(own){if(node!=pointer(0x60d3e0) || uint32_t(pointer(0x5e8e5c)-pointer(0x60d3e4))>100)continue;}
  else if(!flags[0] || !flags[1])continue;
  float distance=m[12]*view[2]+m[13]*view[6]+m[14]*view[10]+view[14];
  if(!std::isfinite(distance) || distance<1 || distance>(profile && profile->capital?250000:20000))continue;
  auto &c=candidates[total++];c.node=node;c.slot=slot;c.distance=distance;c.own=own;c.profile=profile;memcpy(c.matrix,m,sizeof(m));
 }
 // Own engines first; when the budget fills, retain the nearest visible fighters.
 std::sort(candidates,candidates+total,[](const Candidate&a,const Candidate&b){return a.own!=b.own?a.own:a.distance<b.distance;});
 unsigned ships=0;
 for(unsigned i=0;i<total && engine_count<max_engines;++i){
  const auto &c=candidates[i];const float *m=c.matrix;unsigned first=engine_count,per_ship=0;
  float anchors[4][3]={};unsigned anchors_found=0;uintptr_t link=pointer(c.node+0x244);
  for(unsigned limit=0;link && limit<128 && anchors_found<4;++limit,link=pointer(link+8)){
   uintptr_t child=pointer(link+0x10);char name[24]={};
   if(!read_native(pointer(child+0x20),name,23) || !exhaust_name(name))continue;
   if(read_native(child+0xac,anchors[anchors_found],12))++anchors_found;
  }
  bool fallback=anchors_found==0 && c.profile;
  if(fallback){anchors_found=c.profile->count;memcpy(anchors,c.profile->points,sizeof(anchors));}
  float radius=c.profile?c.profile->radius:4.5f,base_length=c.profile?c.profile->length:40.0f;
  for(unsigned anchor=0;anchor<anchors_found && engine_count<max_engines;++anchor){
   const float *local=anchors[anchor];float a[3],b[3],start[4]={},end[4]={};
   if(!std::isfinite(local[0]) || !std::isfinite(local[1]) || !std::isfinite(local[2]))continue;
   for(int j=0;j<3;++j){a[j]=m[12+j]+local[0]*m[j]+local[1]*m[4+j]+local[2]*m[8+j];b[j]=a[j]-m[8+j]*base_length*(1+1.625f*ship_motion[c.slot].power);}
   project_point(a,view,proj,start,radius);project_point(b,view,proj,end,radius);
   if(start[3]<=0 || end[3]<=0)continue;
   float margin=3.5f*fmaxf(start[3],end[3]);
   if(fmaxf(start[0],end[0])+margin<0 || fminf(start[0],end[0])-margin>1 ||
      fmaxf(start[1],end[1])+margin<0 || fminf(start[1],end[1])-margin>1)continue;
   memcpy(engine_start[engine_count],start,sizeof(start));memcpy(engine_end[engine_count],end,sizeof(end));++engine_count;++per_ship;
  }
  if(c.own)player_engine_count=engine_count;
  if(engine_count>first){++ships;if(engine_capture_step){char line[240];sprintf(line,"exhaust slot=%u own=%d engines=%u distance=%.1f power=%.2f uv=%.3f,%.3f profile=%s fallback=%d",c.slot,c.own,engine_count-first,c.distance,ship_motion[c.slot].power,engine_start[first][0],engine_start[first][1],c.profile?c.profile->model:"native",fallback);log(line);}}
 }
 if(engine_capture_step){char line[100];sprintf(line,"exhaust total ships=%u emitters=%u player_emitters=%u",ships,engine_count,player_engine_count);log(line);}
}
static void update_uniforms(){
 runtime->enumerate_uniform_variables("AOAClassic.fx",[](reshade::api::effect_runtime *rt,reshade::api::effect_uniform_variable v){
 char name[80];rt->get_uniform_variable_name(v,name);
 if(strcmp(name,"PreUIActive")==0)rt->set_uniform_value_bool(v,true);
 else if(strcmp(name,"EngineCaptureOff")==0)rt->set_uniform_value_bool(v,engine_capture_step==1 && !fleet_capture);
 else if(strcmp(name,"FleetCaptureOff")==0)rt->set_uniform_value_bool(v,engine_capture_step==1 && fleet_capture);
 else if(strcmp(name,"HazeCaptureOff")==0)rt->set_uniform_value_bool(v,haze_capture_step==1);
 else if(strcmp(name,"HazeCameraValid")==0)rt->set_uniform_value_bool(v,haze_camera_valid);
 else if(strcmp(name,"HazeCameraOrigin")==0)rt->set_uniform_value_float(v,haze_origin,3);
 else if(strcmp(name,"HazeCameraRight")==0)rt->set_uniform_value_float(v,haze_right,3);
 else if(strcmp(name,"HazeCameraUp")==0)rt->set_uniform_value_float(v,haze_up,3);
 else if(strcmp(name,"HazeCameraForward")==0)rt->set_uniform_value_float(v,haze_forward,3);
 else if(strcmp(name,"HazeProjection")==0)rt->set_uniform_value_float(v,haze_projection,4);
 else if(strcmp(name,"HazeCenterA")==0)rt->set_uniform_value_float(v,haze_centers[0],3);
 else if(strcmp(name,"HazeCenterB")==0)rt->set_uniform_value_float(v,haze_centers[1],3);
 else if(strcmp(name,"EngineCount")==0)rt->set_uniform_value_uint(v,engine_count);
 else if(strcmp(name,"PlayerEngineCount")==0)rt->set_uniform_value_uint(v,player_engine_count);
 else if(strcmp(name,"EngineStarts")==0)rt->set_uniform_value_float(v,&engine_start[0][0],max_engines*4);
 else if(strcmp(name,"EngineEnds")==0)rt->set_uniform_value_float(v,&engine_end[0][0],max_engines*4);
 });
}
extern "C" void before_hud(){
 if(!runtime || in_effect || applied)return;
 update_engines();
 update_uniforms();
 auto cmd=runtime->get_command_queue()->get_immediate_command_list();
 auto context=reinterpret_cast<ID3D11DeviceContext*>(cmd->get_native());
 ID3D11DeviceContext1 *ctx1=nullptr;
 if(FAILED(context->QueryInterface(__uuidof(ID3D11DeviceContext1),(void**)&ctx1)))return;
 ID3D11RenderTargetView *rtv=nullptr;context->OMGetRenderTargets(1,&rtv,nullptr);
 if(!rtv){ctx1->Release();return;}
 ID3D11Resource *res=nullptr;rtv->GetResource(&res);
 ID3D11Texture2D *tex=nullptr;
 if(FAILED(res->QueryInterface(__uuidof(ID3D11Texture2D),(void**)&tex))){res->Release();rtv->Release();ctx1->Release();return;}
 D3D11_TEXTURE2D_DESC desc;tex->GetDesc(&desc);tex->Release();res->Release();
 unsigned w,h;runtime->get_screenshot_width_and_height(&w,&h);
 if(desc.Width!=w || desc.Height!=h || desc.SampleDesc.Count!=1){rtv->Release();ctx1->Release();return;}
 ID3D11Device *dev=nullptr;context->GetDevice(&dev);
 ID3D11Device1 *dev1=nullptr;
 if(FAILED(dev->QueryInterface(__uuidof(ID3D11Device1),(void**)&dev1))){dev->Release();rtv->Release();ctx1->Release();return;}
 D3D_FEATURE_LEVEL levels[]={dev->GetFeatureLevel()},chosen;
 ID3DDeviceContextState *clean=nullptr,*saved=nullptr;
 HRESULT hr=dev1->CreateDeviceContextState(0,levels,1,D3D11_SDK_VERSION,__uuidof(ID3D11Device),&chosen,&clean);
 if(SUCCEEDED(hr)){
  ID3D11DepthStencilView *dsv=nullptr;context->OMGetRenderTargets(0,nullptr,&dsv);
  if(dsv){
   D3D11_DEPTH_STENCIL_VIEW_DESC dd;dsv->GetDesc(&dd);ID3D11Resource *dr=nullptr;dsv->GetResource(&dr);
   D3D11_SHADER_RESOURCE_VIEW_DESC sd={};sd.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;sd.Texture2D.MipLevels=1;
   sd.Format=dd.Format==DXGI_FORMAT_D24_UNORM_S8_UINT?DXGI_FORMAT_R24_UNORM_X8_TYPELESS:dd.Format==DXGI_FORMAT_D16_UNORM?DXGI_FORMAT_R16_UNORM:dd.Format==DXGI_FORMAT_D32_FLOAT_S8X24_UINT?DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS:DXGI_FORMAT_R32_FLOAT;
   HRESULT dh=dev->CreateShaderResourceView(dr,&sd,&world_depth);
   if(calls<3){char s[100];sprintf(s,"depth format=%u create=%lx srv=%p",dd.Format,(unsigned long)dh,world_depth);log(s);}
   dr->Release();dsv->Release();
  }else if(calls<3)log("no active depth view");
  in_effect=true;ctx1->SwapDeviceContextState(clean,&saved);
  if(calls++<3){char s[160];sprintf(s,"pre UI: %ux%u target=%p frame=%u",w,h,rtv,frames);log(s);}
  if(world_depth) runtime->render_effects(cmd,{reinterpret_cast<uint64_t>(rtv)},{reinterpret_cast<uint64_t>(rtv)});
  else runtime->render_effects(cmd,{0},{0});
  ctx1->SwapDeviceContextState(saved,nullptr);if(saved)saved->Release();clean->Release();
  if(world_depth){world_depth->Release();world_depth=nullptr;}
  applied=true;in_effect=false;
 }
 dev1->Release();dev->Release();rtv->Release();ctx1->Release();
}
static void effects_begin(reshade::api::effect_runtime *r,reshade::api::command_list *,reshade::api::resource_view,reshade::api::resource_view){
 if(in_effect && world_depth){r->update_texture_bindings("AOA_WORLD_DEPTH",{reinterpret_cast<uint64_t>(world_depth)},{reinterpret_cast<uint64_t>(world_depth)});}
}
extern "C" __attribute__((naked)) void hud_hook(){
 __asm__ volatile("pushfl\n pushal\n movl %esp,%eax\n subl $528,%esp\n andl $-16,%esp\n movl %eax,512(%esp)\n fxsave (%esp)\n call _before_hud\n fxrstor (%esp)\n movl 512(%esp),%esp\n popal\n popfl\n movl 0x198(%esi),%ecx\n pushl $0x44b3cd\n ret\n");
}
static void install(){
 if(installed)return;
 auto site=reinterpret_cast<unsigned char*>(0x44b3c7);
 if(GetModuleHandleW(nullptr)!=(HMODULE)0x400000 || memcmp(site,original,6)!=0){log("signature mismatch; not installed");return;}
 DWORD old;if(!VirtualProtect(site,6,PAGE_EXECUTE_READWRITE,&old))return;
 patch[0]=0xe9;*reinterpret_cast<int*>(patch+1)=reinterpret_cast<unsigned char*>(&hud_hook)-site-5;patch[5]=0x90;memcpy(site,patch,6);
 DWORD ignored;VirtualProtect(site,6,old,&ignored);FlushInstructionCache(GetCurrentProcess(),site,6);installed=true;log("installed world/HUD boundary at 0044B3C7");
}
static void init(reshade::api::effect_runtime *r){runtime=r;install();}
static void destroy(reshade::api::effect_runtime *r){if(runtime==r)runtime=nullptr;}
// Suppress the normal final-screen effect in menus, on unsupported targets, and
// when the native signature is unavailable. This fails closed for UI preservation.
static void presenting(reshade::api::command_queue *q,reshade::api::swapchain *sc,
 const reshade::api::rect *,const reshade::api::rect *,uint32_t,const reshade::api::rect *){
 if(runtime && runtime->get_hwnd()==sc->get_hwnd() && !applied)
  runtime->render_effects(q->get_immediate_command_list(),{0},{0});
}
static void presented(reshade::api::effect_runtime *r){
 runtime=r;++frames;
 // The world hook does not run in menus; reset placement here on flight exit.
 if(pointer(pointer(0x5e6e58)+0x20)!=0x44afd0)haze_seeded=false;
 if(haze_capture_step==1){r->save_screenshot("HazeBefore");haze_capture_step=2;applied=false;return;}
 if(haze_capture_step==2){r->save_screenshot("HazeAfter");haze_capture_step=0;applied=false;return;}
 if(capture_step==0 && engine_capture_step==0 && GetFileAttributesA("classic-haze-capture.flag")!=INVALID_FILE_ATTRIBUTES){
  DeleteFileA("classic-haze-capture.flag");haze_capture_step=1;applied=false;return;
 }
 if(engine_capture_step==1){r->save_screenshot(fleet_capture?"FleetBefore":"EngineBefore");engine_capture_step=2;}
 else if(engine_capture_step==2){r->save_screenshot(fleet_capture?"FleetAfter":"EngineAfter");engine_capture_step=0;}
 else if(capture_step==0 && GetFileAttributesA("classic-fleet-capture.flag")!=INVALID_FILE_ATTRIBUTES){
  DeleteFileA("classic-fleet-capture.flag");fleet_capture=true;engine_capture_step=1;
 }
 else if(capture_step==0 && GetFileAttributesA("classic-engine-capture.flag")!=INVALID_FILE_ATTRIBUTES){
  DeleteFileA("classic-engine-capture.flag");fleet_capture=false;engine_capture_step=1;
 }
 // Explicit opt-in capture: two full frames, with the HUD present in both.
 // They are sequential frames, not a same-frame simulation.
 if(capture_step==1){r->save_screenshot("UIOriginal");r->set_effects_state(capture_enabled);capture_step=2;}
 else if(capture_step==2){r->save_screenshot("UIProtected");capture_step=0;}
 else if(engine_capture_step==0 && GetFileAttributesA("classic-ui-capture.flag")!=INVALID_FILE_ATTRIBUTES){
  DeleteFileA("classic-ui-capture.flag");capture_enabled=r->get_effects_state();
  r->set_effects_state(false);capture_step=1;
 }
 applied=false;
}
extern "C" __declspec(dllexport) const char *NAME="AOA Preserve UI";
BOOL APIENTRY DllMain(HMODULE m,DWORD why,LPVOID){
 if(why==DLL_PROCESS_ATTACH){if(!reshade::register_addon(m))return FALSE;
 reshade::register_event<reshade::addon_event::init_effect_runtime>(init);
 reshade::register_event<reshade::addon_event::destroy_effect_runtime>(destroy);
 reshade::register_event<reshade::addon_event::reshade_present>(presented);
 reshade::register_event<reshade::addon_event::present>(presenting);
 reshade::register_event<reshade::addon_event::reshade_begin_effects>(effects_begin);
 }else if(why==DLL_PROCESS_DETACH){
  if(installed){DWORD old;auto site=(void*)0x44b3c7;if(memcmp(site,patch,6)==0 && VirtualProtect(site,6,PAGE_EXECUTE_READWRITE,&old)){memcpy(site,original,6);DWORD ignored;VirtualProtect(site,6,old,&ignored);FlushInstructionCache(GetCurrentProcess(),site,6);}}
  reshade::unregister_addon(m);
 }return TRUE;
}





