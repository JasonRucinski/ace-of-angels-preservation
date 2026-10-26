<#
.SYNOPSIS
  Register (or unregister) ActiveSkin.ocx for the current user only - no admin.

.DESCRIPTION
  The AoA client's login/station dialogs host SoftShape ActiveSkin 3.60
  ActiveX controls; if they are not registered, MFC throws while creating the
  dialog and the client crashes (0xC000041D). The original Wise installer
  registered the OCX machine-wide. Instead, this calls the OCX's own
  DllRegisterServer from a 32-bit process with HKEY_CLASSES_ROOT overridden to
  HKCU\Software\Classes (RegOverridePredefKey + OaEnablePerUserTLibRegistration),
  the same technique ATL uses for per-user registration. ActiveSkin's .rgs
  scripts write only under HKCR, but its ScriptPlugins object also creates
  HKLM\Software\SoftShape\ActiveSkin\ScriptPlugins directly and fails the whole
  registration if it can't, so HKEY_LOCAL_MACHINE is overridden to HKCU for the
  duration of the call as well. Nothing lands in HKLM.

  The registration records the OCX's absolute path; re-run after moving the
  game folder. Undo with -Unregister.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX
#>
param(
    [Parameter(Mandatory = $true)][string]$Ocx,
    [switch]$Unregister
)
$ErrorActionPreference = "Stop"
$Ocx = (Resolve-Path $Ocx).Path

if ([IntPtr]::Size -ne 4) {
    # The OCX is 32-bit; it can only be loaded into a 32-bit process.
    $ps32 = Join-Path $env:WINDIR "SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Ocx", $Ocx)
    if ($Unregister) { $argList += "-Unregister" }
    & $ps32 @argList
    exit $LASTEXITCODE
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PerUserCom {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
    static extern int RegOpenKeyExW(IntPtr hKey, string subKey, int options, int sam, out IntPtr result);
    [DllImport("advapi32.dll")] static extern int RegOpenCurrentUser(int sam, out IntPtr result);
    [DllImport("advapi32.dll")] static extern int RegOverridePredefKey(IntPtr hKey, IntPtr hNewKey);
    [DllImport("advapi32.dll")] static extern int RegCloseKey(IntPtr hKey);
    [DllImport("oleaut32.dll")] static extern void OaEnablePerUserTLibRegistration();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr LoadLibraryW(string path);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [DllImport("ole32.dll")] static extern int CoInitialize(IntPtr reserved);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int DllRegFn();

    static readonly IntPtr HKCR = new IntPtr(unchecked((int)0x80000000));
    static readonly IntPtr HKCU = new IntPtr(unchecked((int)0x80000001));
    static readonly IntPtr HKLM = new IntPtr(unchecked((int)0x80000002));
    const int KEY_ALL_ACCESS = 0xF003F;

    public static int Run(string path, bool unregister) {
        IntPtr classes, user;
        int rc = RegOpenKeyExW(HKCU, "Software\\Classes", 0, KEY_ALL_ACCESS, out classes);
        if (rc != 0) throw new Exception("RegOpenKeyEx(HKCU\\Software\\Classes) failed: " + rc);
        rc = RegOpenCurrentUser(KEY_ALL_ACCESS, out user);
        if (rc != 0) throw new Exception("RegOpenCurrentUser failed: " + rc);
        IntPtr module = IntPtr.Zero;
        try {
            CoInitialize(IntPtr.Zero);
            OaEnablePerUserTLibRegistration();
            rc = RegOverridePredefKey(HKCR, classes);
            if (rc != 0) throw new Exception("RegOverridePredefKey(HKCR) failed: " + rc);
            rc = RegOverridePredefKey(HKLM, user);
            if (rc != 0) throw new Exception("RegOverridePredefKey(HKLM) failed: " + rc);
            module = LoadLibraryW(path);
            if (module == IntPtr.Zero) throw new Exception("LoadLibrary failed: " + Marshal.GetLastWin32Error());
            IntPtr fn = GetProcAddress(module, unregister ? "DllUnregisterServer" : "DllRegisterServer");
            if (fn == IntPtr.Zero) throw new Exception("export not found");
            return ((DllRegFn)Marshal.GetDelegateForFunctionPointer(fn, typeof(DllRegFn)))();
        } finally {
            RegOverridePredefKey(HKCR, IntPtr.Zero);
            RegOverridePredefKey(HKLM, IntPtr.Zero);
            RegCloseKey(classes);
            RegCloseKey(user);
            if (module != IntPtr.Zero) FreeLibrary(module);
        }
    }
}
"@

$hr = [PerUserCom]::Run($Ocx, [bool]$Unregister)
$verb = if ($Unregister) { "DllUnregisterServer" } else { "DllRegisterServer" }
"{0} returned 0x{1:X8} for {2}" -f $verb, $hr, $Ocx
if ($hr -ne 0) { exit 1 }
