// MIT licensed local diagnostic helper. Requires ReShade 6.8.0 full add-on API.
// Built only for the separate offline capture copy; not part of normal setup.
#include <reshade.hpp>
#include <windows.h>

static unsigned frames = 0;
static bool capturing = false;
static unsigned pairs = 0;

static void begin(reshade::api::effect_runtime *runtime, reshade::api::command_list *,
                  reshade::api::resource_view, reshade::api::resource_view)
{
    unsigned width = 0, height = 0;
    runtime->get_screenshot_width_and_height(&width, &height);
    if (width < 640 || height < 480) return;
    ++frames;
    capturing = pairs < 3 && (frames == 180 || frames == 540 || frames == 900);
    if (capturing) runtime->save_screenshot("Before");
}

static void finish(reshade::api::effect_runtime *runtime, reshade::api::command_list *,
                   reshade::api::resource_view, reshade::api::resource_view)
{
    if (!capturing) return;
    runtime->save_screenshot("After");
    capturing = false;
    ++pairs;
}

extern "C" __declspec(dllexport) const char *NAME = "AOA Same Frame Capture";
extern "C" __declspec(dllexport) const char *DESCRIPTION = "Save three actual before/after frame pairs for the local visual experiment.";

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        if (!reshade::register_addon(module)) return FALSE;
        reshade::register_event<reshade::addon_event::reshade_begin_effects>(begin);
        reshade::register_event<reshade::addon_event::reshade_finish_effects>(finish);
    } else if (reason == DLL_PROCESS_DETACH) {
        reshade::unregister_addon(module);
    }
    return TRUE;
}
