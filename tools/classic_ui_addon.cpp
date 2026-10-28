// MIT licensed. Optional offline ReShade 6.8.0 add-on for the pinned AOA 2.9.2 client.
// Run world effects after 43CCF0 and before the HUD/target-preview draw calls.
#include <reshade.hpp>
#include <windows.h>
#include <d3d11_1.h>
#include <cstdio>
#include <cstring>
static reshade::api::effect_runtime *runtime=nullptr;
static bool installed=false, in_effect=false, applied=false;
static unsigned frames=0, calls=0, capture_step=0;
static bool capture_enabled=false;
static unsigned char patch[6];
static ID3D11ShaderResourceView *world_depth=nullptr;
static const unsigned char original[6]={0x8b,0x8e,0x98,0x01,0x00,0x00};
static void log(const char *s){FILE*f=fopen("classic-ui.log","a");if(f){fprintf(f,"%s\n",s);fclose(f);}}
extern "C" void before_hud(){
 if(!runtime || in_effect || applied)return;
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
 if(in_effect && world_depth){r->update_texture_bindings("AOA_WORLD_DEPTH",{reinterpret_cast<uint64_t>(world_depth)},{reinterpret_cast<uint64_t>(world_depth)});r->enumerate_uniform_variables("AOAClassic.fx",[](reshade::api::effect_runtime *rt,reshade::api::effect_uniform_variable v){char name[80];rt->get_uniform_variable_name(v,name);if(strcmp(name,"PreUIActive")==0)rt->set_uniform_value_bool(v,true);});}
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
 // Explicit opt-in capture: two full frames, with the HUD present in both.
 // They are sequential frames, not a same-frame simulation.
 if(capture_step==1){r->save_screenshot("UIOriginal");r->set_effects_state(capture_enabled);capture_step=2;}
 else if(capture_step==2){r->save_screenshot("UIProtected");capture_step=0;}
 else if(GetFileAttributesA("classic-ui-capture.flag")!=INVALID_FILE_ATTRIBUTES){
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





