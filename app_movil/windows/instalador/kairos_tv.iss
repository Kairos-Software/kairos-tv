; ═══════════════════════════════════════════════════════════════════════
;  El instalador de Kairos TV para PC (Inno Setup 6).
;  Lo arma armar.ps1 (no se compila a mano): le pasa Version, Origen (la
;  carpeta Release con el programa y las bibliotecas de C++) y Salida.
;  Ver README.md.
;
;  - Se instala solo para el usuario, sin permiso de administrador, en
;    %LOCALAPPDATA%\Programs\Kairos TV. Así la app se actualiza sola, en
;    silencio (/VERYSILENT), sin que Windows pida permiso.
;  - La sesión y lo guardado (catálogo, favoritos) quedan en
;    %APPDATA%\Kairos Software: no se tocan al actualizar ni al desinstalar.
;  - Antes de reemplazar archivos espera a que la app se cierre (su marca
;    «KairosTVAbierta», windows/runner/main.cpp) y al terminar la abre.
; ═══════════════════════════════════════════════════════════════════════

#ifndef Version
  #error Falta /DVersion: el instalador se arma con armar.ps1
#endif
#ifndef Origen
  #error Falta /DOrigen
#endif
#ifndef Salida
  #error Falta /DSalida
#endif

[Setup]
AppId={{B3A1F0E2-7C4D-4E8B-9A26-5D1C8F3E7B40}
AppName=Kairos TV
AppVersion={#Version}
AppVerName=Kairos TV {#Version}
AppPublisher=Kairos Software
VersionInfoVersion={#Version}
VersionInfoDescription=Instalador de Kairos TV para PC
DefaultDirName={localappdata}\Programs\Kairos TV
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#Salida}
OutputBaseFilename=KairosTV-{#Version}
SetupIconFile=..\runner\resources\app_icon.ico
UninstallDisplayIcon={app}\KairosTV.exe
UninstallDisplayName=Kairos TV
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Poner un acceso directo en el escritorio"

; Cada actualización deja el programa entero, sin restos de la versión anterior (la sesión está en otro lado)
[InstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: files; Name: "{app}\*.dll"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Kairos TV"; Filename: "{app}\KairosTV.exe"; WorkingDir: "{app}"; Comment: "Canales en vivo, películas y series"
Name: "{userdesktop}\Kairos TV"; Filename: "{app}\KairosTV.exe"; WorkingDir: "{app}"; Tasks: escritorio

[Run]
; Al terminar se abre (también al actualizarse sola: así vuelve a la pantalla). /SINABRIR=1 no la abre (pruebas).
Filename: "{app}\KairosTV.exe"; Description: "Abrir Kairos TV"; Flags: postinstall nowait; Check: Abrirla

[Code]
const
  MARCA = 'KairosTVAbierta';

function Abrirla: Boolean;
begin
  Result := ExpandConstant('{param:SINABRIR|0}') <> '1';
end;

// Espera a que Kairos TV se cierre. Al actualizarse sola (en silencio), la app se cierra apenas abre este
// instalador: se la espera hasta 1 minuto. A mano, se pide cerrarla.
function InitializeSetup: Boolean;
var
  Vueltas: Integer;
begin
  Result := True;
  Vueltas := 0;
  while CheckForMutexes(MARCA) do
  begin
    if WizardSilent then
    begin
      if Vueltas >= 120 then
      begin
        Log('Kairos TV sigue abierta: no se instala.');
        Result := False;
        Exit;
      end;
      Sleep(500);
      Vueltas := Vueltas + 1;
    end
    else if MsgBox('Kairos TV está abierta. Cerrala y tocá Aceptar para seguir.', mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;
