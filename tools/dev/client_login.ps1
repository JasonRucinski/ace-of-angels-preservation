<#
.SYNOPSIS
  Fill the running AoA client's login dialog and press Play Online (test driver).

.DESCRIPTION
  Sends WM_SETTEXT to the dialog's Handle, Password and Station IP edit boxes
  (ordered top to bottom) and posts the hidden "Play Online" button's
  WM_COMMAND, so the client logs in to a local tools\station_stub.py without
  touching the mouse. Use test values only; the client sends the password
  protected only by the static packet cipher.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\client_login.ps1 -Station 127.0.0.1
#>
param([string]$Handle = "testpilot", [string]$Password = "test", [string]$Station = "127.0.0.1")
Add-Type @"
using System; using System.Collections.Generic; using System.Runtime.InteropServices; using System.Text;
public static class LG {
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
  [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Ansi)] static extern IntPtr SendMessageA(IntPtr h, uint m, IntPtr w, string l);
  [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  static string Cls(IntPtr h) { var s = new StringBuilder(64); GetClassName(h, s, 64); return s.ToString(); }
  static string Txt(IntPtr h) { var s = new StringBuilder(64); GetWindowText(h, s, 64); return s.ToString(); }
  public static string Login(uint pid, string handle, string pw, string station) {
    IntPtr dlg = IntPtr.Zero;
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && Cls(h) == "#32770" && Txt(h).StartsWith("Ace of Angels")) dlg = h; return true; }, IntPtr.Zero);
    if (dlg == IntPtr.Zero) return "login dialog not found";
    var edits = new List<IntPtr>(); IntPtr play = IntPtr.Zero;
    EnumChildWindows(dlg, (c, l) => {
      if (Cls(c) == "Edit") edits.Add(c);
      if (Cls(c) == "Button" && Txt(c) == "Play Online") play = c;
      return true; }, IntPtr.Zero);
    edits.Sort((a, b) => { RECT ra, rb; GetWindowRect(a, out ra); GetWindowRect(b, out rb); return ra.T.CompareTo(rb.T); });
    if (edits.Count < 3 || play == IntPtr.Zero) return "controls not found (" + edits.Count + " edits)";
    SendMessageA(edits[0], 0x000C, IntPtr.Zero, handle);
    SendMessageA(edits[1], 0x000C, IntPtr.Zero, pw);
    SendMessageA(edits[2], 0x000C, IntPtr.Zero, station);
    PostMessage(dlg, 0x0111, new IntPtr(GetDlgCtrlID(play) & 0xFFFF), play);
    return String.Format("filled handle/password/station={0}, pressed Play Online (id {1})", station, GetDlgCtrlID(play));
  }
}
"@
$p = Get-Process -Name AOACLIENT -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { "process not running"; exit 1 }
[LG]::Login([uint32]$p.Id, $Handle, $Password, $Station)
