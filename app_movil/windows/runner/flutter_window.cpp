#include "flutter_window.h"

#include <flutter/standard_method_codec.h>

#include <optional>
#include <string>

#include "flutter/generated_plugin_registrant.h"

namespace {

// El tamaño mínimo de la ventana (en píxeles de 96 ppp): más chica, el diseño de la tele (1920×1080 escalado)
// quedaría ilegible.
constexpr int kAnchoMinimo = 960;
constexpr int kAltoMinimo = 540;

}  // namespace

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  // lib/pc.dart
  canal_ = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "kairos/ventana",
      &flutter::StandardMethodCodec::GetInstance());
  canal_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& llamada,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> resultado) {
        if (llamada.method_name() == "pantallaCompleta") {
          const auto* completa = std::get_if<bool>(llamada.arguments());
          if (completa != nullptr) {
            PonerPantallaCompleta(*completa);
          }
          resultado->Success(flutter::EncodableValue(pantalla_completa_));
        } else if (llamada.method_name() == "version") {
          resultado->Success(flutter::EncodableValue(std::string(FLUTTER_VERSION)));
        } else {
          resultado->NotImplemented();
        }
      });

  // Abre maximizada, como una tele que ocupa la pantalla (la barra de título queda: se puede achicar o cerrar).
  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    ShowWindow(GetHandle(), SW_SHOWMAXIMIZED);
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  canal_ = nullptr;
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

void FlutterWindow::PonerPantallaCompleta(bool completa) {
  HWND ventana = GetHandle();
  if (ventana == nullptr || completa == pantalla_completa_) {
    return;
  }
  const LONG estilo = GetWindowLong(ventana, GWL_STYLE);
  if (completa) {
    MONITORINFO monitor = {sizeof(MONITORINFO)};
    if (!GetWindowPlacement(ventana, &lugar_anterior_) ||
        !GetMonitorInfo(MonitorFromWindow(ventana, MONITOR_DEFAULTTONEAREST), &monitor)) {
      return;
    }
    // Sin borde ni barra de título, del tamaño exacto del monitor: Windows la reconoce como pantalla completa y
    // esconde la barra de tareas mientras está adelante.
    SetWindowLong(ventana, GWL_STYLE, estilo & ~WS_OVERLAPPEDWINDOW);
    SetWindowPos(ventana, HWND_TOP, monitor.rcMonitor.left, monitor.rcMonitor.top,
                 monitor.rcMonitor.right - monitor.rcMonitor.left,
                 monitor.rcMonitor.bottom - monitor.rcMonitor.top,
                 SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
  } else {
    SetWindowLong(ventana, GWL_STYLE, estilo | WS_OVERLAPPEDWINDOW);
    SetWindowPlacement(ventana, &lugar_anterior_);
    SetWindowPos(ventana, nullptr, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
  }
  pantalla_completa_ = completa;
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
    case WM_GETMINMAXINFO: {
      auto* medidas = reinterpret_cast<MINMAXINFO*>(lparam);
      const UINT ppp = GetDpiForWindow(hwnd);
      medidas->ptMinTrackSize.x = MulDiv(kAnchoMinimo, ppp, 96);
      medidas->ptMinTrackSize.y = MulDiv(kAltoMinimo, ppp, 96);
      return 0;
    }
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
