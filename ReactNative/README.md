# 🍫 ICChocolate — Aplicación Móvil (React Native & Expo)

Aplicación móvil oficial de **ICChocolate** para la gestión de inventario artesanal, control de calidad térmico mediante sensores IoT (ESP32 / DHT11), reconocimiento de documentos con Gemini Vision y auditoría de movimientos.

Desarrollada sobre **React Native 0.88**, **React 19** y **Expo SDK 58**, compatible con **Android** e **iOS** a través de **Expo Go**.

---

## 📋 Requisitos Previos

1. **Node.js** (v18 o superior) y **npm**.
2. **Teléfono Móvil (Android o iOS)** con la aplicación **Expo Go** instalada:
   - [Expo Go en Google Play Store](https://play.google.com/store/apps/details?id=host.exp.exponent)
   - [Expo Go en Apple App Store](https://apps.apple.com/app/expo-go/id982107779)
3. **Backend de Django y Base de Datos (Docker)** corriendo en tu computadora:
   ```bash
   cd ..
   docker compose up -d
   ```
4. **Misma Red Wi-Fi**: Tu computadora y tu teléfono deben estar conectados a la misma red local (Wi-Fi).

---

## ⚙️ Configuración de la IP del Backend

Antes de iniciar la app, asegúrate de que la dirección IP de tu computadora en la red local esté configurada en [`src/api.js`](./src/api.js):

```javascript
// src/api.js (Línea 9)
const API_BASE = 'http://192.168.18.126:8003/api/mobile';
```

> [!TIP]
> **¿Cambiaste de red Wi-Fi o estás en otra ubicación?**  
> 1. Averigua la IP local de tu PC ejecutando en Linux: `hostname -I` (o `ip a`).  
> 2. Reemplaza esa IP en `src/api.js`.  
> 3. Asegúrate de que esa misma IP esté listada en el archivo `.env` de la raíz en `DJANGO_ALLOWED_HOSTS`.

---

## 🚀 Cómo Ejecutar la Aplicación

### 1. Entrar a la carpeta del proyecto móvil
```bash
cd /ICChocolate/ReactNative
```

### 2. Instalar dependencias (solo la primera vez)
```bash
npm install
```

### 3. Iniciar el servidor Metro / Expo
```bash
npx expo start
```
*(Si alguna vez realizas cambios estructurales y deseas limpiar la caché del bundler, ejecuta: `npx expo start -c`)*.

### 4. Abrir en tu Teléfono
1. Verás un **código QR** grande en tu terminal.
2. Abre la app **Expo Go** en tu celular.
3. Selecciona **"Scan QR Code"** y apunta la cámara de tu celular al código QR de la terminal.
4. El paquete de JavaScript se descargará a través del puerto `8081` y la app se abrirá en tu pantalla.

---

## 🔑 Credenciales de Acceso Demo

La pantalla de bienvenida incluye botones de **Acceso Rápido** para ingresar en 1 toque sin escribir credenciales:

| Rol | Botón de Acceso | Correo Electrónico | Contraseña | Permisos |
|---|---|---|---|---|
| **Dueño** | `👑 Cuenta Dueño` | `dueno@icchocolate.local` | `OwnerPass!2026` | Acceso total: inventario, configuración, mermas, conversión y sensores |
| **Empleado** | `👤 Cuenta Empleado` | `empleado@icchocolate.local` | `EmpPass!2026` | Operaciones de tienda: compras, ventas, traslados y stock |

---

## 📱 Funcionalidades y Pestañas Principales

La barra inferior cuenta con 6 pestañas organizadas para la operación diaria:

### 1. 🏠 Inicio (`HomeScreen`)
- **Temperatura en Vivo**: Muestra la medición actual del sensor DHT11 en Almacén (ej. `8.8 °C` y `58.4 %`). Tocar la tarjeta te lleva directo a Monitoreo.
- **Ubicación de Tienda con GPS**: Utiliza geolocalización satelital (`expo-location`) para validar en qué sucursal física se encuentra el usuario.
- **Resumen Ejecutivo**: Total de unidades disponibles, productos activos y accesos directos.

### 2. 📦 Stock (`StockScreen`)
- **Buscador Reactivo Instantáneo**: Filtra en tiempo real por nombre de producto, código de presentación (`BARRA-100`, `POLVO-1000`, `CHISPAS-100`), descripción o ubicación.
- **Filtros Rápidos**: Chips para ver `Todos`, `📦 Almacén` o `🏪 Display`.
- **Alertas de Stock**: Indicador visual para presentaciones con stock bajo (≤ 5 unidades).

### 3. 📸 Registro y Operaciones (`CameraScreen`)
Hub central para movimientos de almacén organizado en 4 modos:
- **📸 Con Foto (IA)**: Fotografía boletas o etiquetas. Gemini Vision extrae los renglones automáticamente para su revisión antes de confirmar.
- **✍️ Manual**: Formulario ágil para registrar Compras, Ventas, Traslados, Mermas, Consumos y Ajustes.
- **🔄 Convertir**: Transformación entre presentaciones (ej. *1 Caja de 12 barras ➔ 12 Barras individuales*) con cálculo dinámico en pantalla.
- **📋 Borradores**: Lista de movimientos preparados pendientes de confirmación o cancelación atómica.

### 4. 📜 Historial (`HistoryScreen`)
- **Auditoría de Movimientos**: Registro completo con fecha, responsable (`Dueño` / `Empleado`), tipo y motivo.
- **Deltas de Inventario**: Muestra las variaciones netas de existencias (`+24`, `+12`, `-1`) y ubicación afectada.
- **Filtros por Operación**: Carga Inicial, Compra, Venta, Traslado, Merma y Ajuste.

### 5. 📡 Monitoreo IoT (`MonitoringScreen`)
- **Selector de Sensores ESP32**: Permite alternar entre los microcontroladores registrados.
- **Estado de Comunicación**: Badge `🟢 En Línea` vs `🔴 Desconectado` (ventana de 180 s).
- **Semáforo Térmico de Calidad**:
  - `🛡️ ≤ 10.0 °C`: Conservación óptima de chocolate fino de cacao.
  - `⚠️ > 10.0 °C`: Alerta de riesgo de derretimiento.
- **Historial de Ciclos**: Tabla de las últimas 30 telemetrías con hora, temperatura, humedad y muestras válidas (`4/4`).

### 6. ⚙️ Herramientas (`ToolsScreen`)
- **💬 Asistente IA**: Chatbot inteligente para consultas de inventario en lenguaje natural.
- **🌐 Portal Web Django**: Consola web completa de administración embebida en WebView sin salir del móvil.
- **ℹ️ Diagnóstico Técnico**: Verificación de IP de backend, motor de base de datos PostgreSQL y Gateway ESP32.
- **🚪 Cerrar Sesión**: Limpieza segura de tokens JWT en el almacenamiento local (`AsyncStorage`).

---

## 🛠️ Solución de Problemas Frecuentes

### ❌ Error: "No se pudo conectar al servidor"
1. Verifica que los contenedores de Docker estén encendidos:
   ```bash
   docker compose ps
   ```
2. Asegúrate de que el firewall de tu PC permita conexiones en los puertos 8003 y 8081:
   ```bash
   sudo ufw allow 8003/tcp
   sudo ufw allow 8081/tcp
   ```
3. Verifica que tu celular esté conectado a la **misma red Wi-Fi** que tu PC (no con datos móviles 4G/5G).
4. Comprueba que la IP de tu PC no haya cambiado ejecutando `hostname -I` y que coincida con `src/api.js`.

### ❌ Advertencias de Push Notifications en Expo Go
En terminal verás una advertencia informativa de Expo Go (`Push notifications are unavailable in Expo Go on Android since SDK 53`). Esto es normal en el entorno de pruebas de Expo Go; la aplicación utiliza **notificaciones locales nativas** en primer plano para alertar si la temperatura supera los 10 °C.

---

## 📂 Estructura del Código

```text
ReactNative/
├── App.js                   # Navegación principal (Tabs + Stack Navigator)
├── app.json                 # Configuración de Expo y permisos (Cámara, GPS)
├── package.json             # Dependencias (Expo SDK 58, React 19)
├── assets/                  # Íconos y pantallas splash
└── src/
    ├── api.js               # Cliente HTTP Axios con interceptores JWT
    ├── notifications.js     # Gestor de notificaciones locales y push
    ├── context/
    │   └── AuthContext.js   # Estado global de autenticación y tokens
    └── screens/
        ├── LoginScreen.js       # Inicio de sesión con atajos demo
        ├── HomeScreen.js        # Pantalla principal con sensor en vivo y GPS
        ├── StockScreen.js       # Catálogo con buscador reactivo multi-campo
        ├── CameraScreen.js      # Operaciones (Foto IA, Manual, Conversión, Borradores)
        ├── HistoryScreen.js     # Historial de movimientos y deltas
        ├── MonitoringScreen.js  # Telemetría de sensores ESP32 en tiempo real
        ├── ToolsScreen.js       # Menú de herramientas y perfil
        ├── ChatScreen.js        # Asistente IA conversacional
        └── WebScreen.js         # Vista WebView del portal web Django
```

