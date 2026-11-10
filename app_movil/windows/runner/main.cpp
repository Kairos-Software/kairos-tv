#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>

#include "flutter_window.h"
#include "utils.h"

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Una sola Kairos TV abierta: si ya hay una, se la trae adelante y esta no abre otra (dos ventanas
  // reproduciendo a la vez). La marca también le dice al instalador (instalador/kairos_tv.iss) que la app
  // sigue abierta: espera a que se cierre antes de reemplazar los archivos. Windows la suelta al cerrarse.
  ::CreateMutexW(nullptr, FALSE, L"KairosTVAbierta");
  if (::GetLastError() == ERROR_ALREADY_EXISTS) {
    HWND abierta = ::FindWindowW(L"FLUTTER_RUNNER_WIN32_WINDOW", L"Kairos TV");
    if (abierta != nullptr) {
      if (::IsIconic(abierta)) {
        ::ShowWindow(abierta, SW_RESTORE);
      }
      ::SetForegroundWindow(abierta);
    }
    return EXIT_SUCCESS;
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  // Kairos TV para PC: abre maximizada (flutter_window.cpp); al achicarla queda en 16:9, del tamaño de abajo.
  // El diseño de la tele (lib/tv/) se escala a la ventana.
  FlutterWindow window(project);
  Win32Window::Point origin(40, 40);
  Win32Window::Size size(1280, 720);
  if (!window.Create(L"Kairos TV", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  return EXIT_SUCCESS;
}
