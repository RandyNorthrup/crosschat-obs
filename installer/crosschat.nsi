; CrossChat setup: installs CrossChat for the current Windows user, without administrator rights, with its own Python.
; installer\build.ps1 builds it and passes VERSION (x.y.z), STAGE (the folder laid out as installed) and OUTFILE.
;
;   setup.exe /S         installs silently (says yes to switching on OBS's WebSocket server when it's off)
;   uninstall.exe /S     removes CrossChat silently (keeps settings and themes in Documents\CrossChat backup)

Unicode true
ManifestDPIAware true
RequestExecutionLevel user
SetCompressor /SOLID lzma

!ifndef VERSION
  !error "VERSION is passed by installer\build.ps1"
!endif
!ifndef STAGE
  !error "STAGE is passed by installer\build.ps1"
!endif
!ifndef OUTFILE
  !error "OUTFILE is passed by installer\build.ps1"
!endif

!define APP "CrossChat"
!define PUBLISHER "Randy Northrup"
!define HOMEPAGE "https://github.com/RandyNorthrup/crosschat-obs"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\CrossChat"
!define PS 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File'

Name "${APP}"
Caption "${APP} ${VERSION} setup"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\CrossChat"
BrandingText "${APP} ${VERSION}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

; Version information on the setup program (SignPath checks product name and version)
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} setup"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "MIT License, ${PUBLISHER}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define MUI_ICON "${STAGE}\hub\web\crosschat.ico"
!define MUI_UNICON "${STAGE}\hub\web\crosschat.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "CrossChat ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Every stream chat in one window for OBS Studio: read and reply to Twitch, YouTube, Kick, X, TikTok, Facebook, Instagram and Rumble, moderate Twitch, YouTube and Kick, and put chat, featured messages, viewer counts and alerts on your stream.$\r$\n$\r$\nCrossChat installs for your Windows account only, brings its own Python, and needs no administrator rights.$\r$\n$\r$\nUpdating? Your settings, themes, sign-ins and chat history are kept. Close nothing: setup restarts CrossChat for an open OBS."
!insertmacro MUI_PAGE_WELCOME

!define MUI_PAGE_HEADER_TEXT "Privacy"
!define MUI_PAGE_HEADER_SUBTEXT "What CrossChat connects to, and what setup changes"
!define MUI_LICENSEPAGE_TEXT_TOP "Please read how CrossChat handles your data."
!define MUI_LICENSEPAGE_TEXT_BOTTOM "CrossChat is free software under the MIT License (LICENSE in its folder)."
!define MUI_LICENSEPAGE_BUTTON "&Next >"
!insertmacro MUI_PAGE_LICENSE "${STAGE}\installer\privacy.txt"

!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "CrossChat is installed"
!define MUI_FINISHPAGE_TEXT "Set your channels in CrossChat's Settings.$\r$\n$\r$\nThen add the script to OBS: Tools > Scripts > +, and pick $INSTDIR\obs\crosschat.lua (its path is on your clipboard)."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION OpenCrossChat
!define MUI_FINISHPAGE_RUN_TEXT "Open CrossChat"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\docs\first-steps.html"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Show how to add CrossChat to OBS"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Function OpenCrossChat
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\hub\control.py" show'
FunctionEnd

Section "CrossChat" SecMain
  SectionIn RO
  SetShellVarContext current
  InitPluginsDir

  ; CrossChat may be running (for OBS, or the demo): stop it before its files are replaced
  File "/oname=$PLUGINSDIR\steps.ps1" "${STAGE}\installer\steps.ps1"
  DetailPrint "Stopping CrossChat if it's running"
  nsExec::ExecToLog '${PS} "$PLUGINSDIR\steps.ps1" -Step stop-hub -App "$INSTDIR"'
  Pop $0

  ; The program folders are replaced whole. Your files (config.json, themes, sign-ins, chat history) live beside them
  ; and are left alone.
  RMDir /r "$INSTDIR\hub"
  RMDir /r "$INSTDIR\extension"
  RMDir /r "$INSTDIR\obs"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\docs"
  RMDir /r "$INSTDIR\installer"
  RMDir /r "$INSTDIR\scripts"              ; from a zip install: setup's uninstaller replaces Uninstall.cmd
  Delete "$INSTDIR\Uninstall.cmd"
  Delete "$INSTDIR\Install.cmd"

  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*.*"

  ; Start menu
  Delete "$SMPROGRAMS\CrossChat\*.lnk"
  CreateDirectory "$SMPROGRAMS\CrossChat"
  !define PYW "$INSTDIR\python\pythonw.exe"
  !define ICON "$INSTDIR\hub\web\crosschat.ico"
  CreateShortCut "$SMPROGRAMS\CrossChat\Open chat.lnk" "${PYW}" '"$INSTDIR\hub\control.py" show' "${ICON}" 0 SW_SHOWNORMAL "" "Open the CrossChat window"
  CreateShortCut "$SMPROGRAMS\CrossChat\Try the demo.lnk" "${PYW}" '"$INSTDIR\hub\control.py" demo' "${ICON}" 0 SW_SHOWNORMAL "" "CrossChat with a made-up live stream; nothing is posted anywhere"
  CreateShortCut "$SMPROGRAMS\CrossChat\Theme Studio.lnk" "${PYW}" '"$INSTDIR\hub\control.py" studio' "${ICON}" 0 SW_SHOWNORMAL "" "Change how chat looks on stream"
  CreateShortCut "$SMPROGRAMS\CrossChat\Go live on X.lnk" "${PYW}" '"$INSTDIR\hub\control.py" x-live' "${ICON}" 0 SW_SHOWNORMAL "" "Start the X livestream now"
  CreateShortCut "$SMPROGRAMS\CrossChat\Test X (never goes live).lnk" "${PYW}" '"$INSTDIR\hub\control.py" x-dry' "${ICON}" 0 SW_SHOWNORMAL "" "Fill in the X form without going live"
  CreateShortCut "$SMPROGRAMS\CrossChat\Hide featured message.lnk" "${PYW}" '"$INSTDIR\hub\control.py" unfeature' "${ICON}" 0 SW_SHOWNORMAL "" "Take the featured message off the stream"
  CreateShortCut "$SMPROGRAMS\CrossChat\CrossChat folder.lnk" "$WINDIR\explorer.exe" '"$INSTDIR"' "${ICON}" 0 SW_SHOWNORMAL "" "Settings, themes and the log"
  CreateShortCut "$SMPROGRAMS\CrossChat\First steps.lnk" "$INSTDIR\docs\first-steps.html" "" "${ICON}" 0 SW_SHOWNORMAL "" "How to add CrossChat to OBS"
  CreateShortCut "$SMPROGRAMS\CrossChat\Uninstall CrossChat.lnk" "$INSTDIR\uninstall.exe" "" "${ICON}" 0 SW_SHOWNORMAL "" "Remove CrossChat"

  ; Apps & features
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "${ICON}"
  WriteRegStr HKCU "${UNINSTKEY}" "URLInfoAbout" "${HOMEPAGE}"
  WriteRegStr HKCU "${UNINSTKEY}" "HelpLink" "${HOMEPAGE}#troubleshooting"
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" $0

  ; OBS's WebSocket server: CrossChat follows the stream through it
  StrCpy $1 ""
  nsExec::ExecToStack '${PS} "$INSTDIR\installer\steps.ps1" -Step obs-status'
  Pop $0
  Pop $2
  ${If} $2 == "off"
    MessageBox MB_YESNO|MB_ICONQUESTION "CrossChat follows OBS through OBS's WebSocket server, which is off.$\r$\n$\r$\nTurn it on now? (It gets a password; CrossChat reads it from OBS.)" /SD IDYES IDNO +2
    StrCpy $1 "-EnableWebSocket"
  ${ElseIf} $2 == "running"
    MessageBox MB_OK|MB_ICONINFORMATION "OBS's WebSocket server is off. In OBS: Tools > WebSocket Server Settings > tick Enable WebSocket server > OK." /SD IDOK
  ${EndIf}

  DetailPrint "Finishing: settings, OBS, the script's path on the clipboard"
  nsExec::ExecToLog '${PS} "$INSTDIR\installer\steps.ps1" -Step finish -App "$INSTDIR" $1'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "CrossChat is installed, but a last step didn't finish ($0). Start menu > CrossChat > Open chat, and check the log in the CrossChat folder." /SD IDOK
  ${EndIf}
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  StrCpy $1 ""
  MessageBox MB_YESNO|MB_ICONQUESTION "Keep your settings and themes in Documents\CrossChat backup?" /SD IDYES IDNO +2
  StrCpy $1 "-Backup"
  ${If} ${FileExists} "$INSTDIR\installer\steps.ps1"
    nsExec::ExecToLog '${PS} "$INSTDIR\installer\steps.ps1" -Step uninstall -App "$INSTDIR" $1'
    Pop $0
  ${EndIf}

  ; Only a CrossChat folder is removed whole: never anything this uninstaller didn't come with.
  ${If} ${FileExists} "$INSTDIR\hub\control.py"
  ${AndIf} ${FileExists} "$INSTDIR\uninstall.exe"
    RMDir /r "$INSTDIR"
  ${EndIf}
  RMDir /r "$SMPROGRAMS\CrossChat"
  DeleteRegKey HKCU "${UNINSTKEY}"
  MessageBox MB_OK|MB_ICONINFORMATION "CrossChat is removed. Two things only you can remove:$\r$\n  - OBS: Tools > Scripts, select crosschat.lua, press the minus button.$\r$\n  - Chrome or Edge: the extensions page, CrossChat, Remove." /SD IDOK
SectionEnd
