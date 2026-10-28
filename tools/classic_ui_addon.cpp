// MIT licensed. Optional offline ReShade 6.8.0 add-on for the pinned AOA 2.9.2 client.
// Run world effects after 43CCF0 and before the HUD/target-preview draw calls.
#include <reshade.hpp>
#include <windows.h>
#include <d3d11_1.h>
#include <cstdio>
#include <cstring>
#include <cmath>

static reshade::api::effect_runtime *runtime=nullptr;
static bool installed=false, in_effect=false, applied=false;
static unsigned frames=0, calls=0, capture_step=0;
static bool capture_enabled=false;
static unsigned engine_capture_step=0;
static unsigned char patch[6];
static ID3D11ShaderResourceView *world_depth=nullptr;
static const unsigned char original[6]={0x8b,0x8e,0x98,0x01,0x00,0x00};
static void log(const char *s){FILE*f=fopen("classic-ui.log","a");if(f){fprintf(f,"%s\n",s);fclose(f);}}
// Only read native state. No physics, asset, or input changes.
static float engine_start[2][4]={}, engine_end[2][4]={};
static bool read_native(uintptr_t address,void *out,size_t count){
 SIZE_T got=0;return address && ReadProcessMemory(GetCurrentProcess(),(void*)address,out,count,&got) && got==count;
}
static uintptr_t pointer(uintptr_t address){uintptr_t p=0;read_native(address,&p,sizeof(p));return p;}
static void project_point(const float *p,const float *view,const float *proj,float *out){
 float q[4]={},c[4]={};
 for(int j=0;j<4;++j)q[j]=p[0]*view[j]+p[1]*view[4+j]+p[2]*view[8+j]+view[12+j];
 for(int j=0;j<4;++j)for(int k=0;k<4;++k)c[j]+=q[k]*proj[k*4+j];
 if(c[3]<=1 || !std::isfinite(c[3])){out[3]=0;return;}
 out[0]=0.5f+0.5f*c[0]/c[3];out[1]=0.5f-0.5f*c[1]/c[3];out[2]=c[2]/c[3];out[3]=fabsf(proj[5]*4.5f/c[3]);
}
static void update_engines(){
 memset(engine_start,0,sizeof(engine_start));memset(engine_end,0,sizeof(engine_end));
 uintptr_t app=pointer(0x5e6e58),world=pointer(0x5e7728),node=pointer(world+0xd3448);
 bool probe=engine_capture_step!=0;
 if(probe){char line[160];sprintf(line,"engine capture node=%lx cached=%lx tick=%u cachedtick=%u",(unsigned long)node,(unsigned long)pointer(0x60d3e0),(unsigned)pointer(0x5e8e5c),(unsigned)pointer(0x60d3e4));log(line);}
 // The native clock advances during a moving frame (observed 1-2 ms).
 // Accept its fresh chase record; reject stale spectator/menu records.
 if(!node || node!=pointer(0x60d3e0) || uint32_t(pointer(0x5e8e5c)-pointer(0x60d3e4))>100)return;
 uintptr_t gfx=pointer(app+0x138);auto device=(void*)pointer(gfx+0x188);
 if(!device)return;
 // IDirect3DDevice7::GetTransform is vtable slot 12 (legacy d3d.h).
 using GetTransform=HRESULT(WINAPI*)(void*,DWORD,float*);
 auto get_transform=(GetTransform)((void**)*(void***)device)[12];
 float view[16],proj[16];
 if(FAILED(get_transform(device,2,view)) || FAILED(get_transform(device,3,proj)))return;
 float m[16];if(!read_native(node+0x7c,m,sizeof(m)))return;
 if(probe){char line[240];sprintf(line,"engine coordinates pos=%g,%g,%g viewpos=%g,%g,%g",m[12],m[13],m[14],view[12],view[13],view[14]);log(line);}
 // Motion response uses rendered position; it does not pretend to read throttle.
 static uintptr_t last_node=0;static float previous[3]={},power=0;static DWORD last_time=0;
 DWORD now=GetTickCount();float dt=(now-last_time)*0.001f;
 if(node==last_node && dt>0 && dt<0.25f){float speed=0;for(int i=0;i<3;++i)speed+=(m[12+i]-previous[i])*m[8+i]/dt;
  float target=fminf(fabsf(speed)/250.0f,1.0f);power+=(target-power)*fminf(dt*4.0f,1.0f);
 }else power=0;
 last_node=node;last_time=now;memcpy(previous,m+12,12);
 uintptr_t link=pointer(node+0x244);int count=0;
 for(int limit=0;link && limit<64 && count<2;++limit,link=pointer(link+8)){
  uintptr_t child=pointer(link+0x10);char name[8]={};
  if(!read_native(pointer(child+0x20),name,7) || _strnicmp(name,"trail",5)!=0)continue;
  float local[3],a[3],b[3];if(!read_native(child+0xac,local,sizeof(local)))continue;
  for(int j=0;j<3;++j){a[j]=m[12+j]+local[0]*m[j]+local[1]*m[4+j]+local[2]*m[8+j];b[j]=a[j]-m[8+j]*(40.0f+65.0f*power);}
  // The native view matrix already includes the absolute camera translation.
  project_point(a,(float*)&view,(float*)&proj,engine_start[count]);
  project_point(b,(float*)&view,(float*)&proj,engine_end[count]);
  if(calls<3 || probe){char line[180];sprintf(line,"engine %d uv %.3f %.3f z %.6f radius %.4f end %.3f %.3f",count,engine_start[count][0],engine_start[count][1],engine_start[count][2],engine_start[count][3],engine_end[count][0],engine_end[count][1]);log(line);}
  ++count;
 }
}
static void update_uniforms(){
 runtime->enumerate_uniform_variables("AOAClassic.fx",[](reshade::api::effect_runtime *rt,reshade::api::effect_uniform_variable v){char name[80];rt->get_uniform_variable_name(v,name);if(strcmp(name,"PreUIActive")==0)rt->set_uniform_value_bool(v,true);
 else if(strcmp(name,"EngineCaptureOff")==0)rt->set_uniform_value_bool(v,engine_capture_step==1);
 else if(strcmp(name,"EngineStart0")==0)rt->set_uniform_value_float(v,engine_start[0],4);
 else if(strcmp(name,"EngineStart1")==0)rt->set_uniform_value_float(v,engine_start[1],4);
 else if(strcmp(name,"EngineEnd0")==0)rt->set_uniform_value_float(v,engine_end[0],4);
 else if(strcmp(name,"EngineEnd1")==0)rt->set_uniform_value_float(v,engine_end[1],4);});
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
 if(engine_capture_step==1){r->save_screenshot("EngineBefore");engine_capture_step=2;}
 else if(engine_capture_step==2){r->save_screenshot("EngineAfter");engine_capture_step=0;}
 else if(capture_step==0 && GetFileAttributesA("classic-engine-capture.flag")!=INVALID_FILE_ATTRIBUTES){
  DeleteFileA("classic-engine-capture.flag");engine_capture_step=1;
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





