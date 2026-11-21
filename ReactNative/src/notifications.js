import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { registerExpoPushToken } from './api';

/**
 * Configura el handler de notificaciones en primer plano.
 */
export function configurePushHandler() {
  // Mostrar notificación incluso cuando la app está abierta
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });
}

/**
 * Registra el dispositivo para notificaciones push de Expo
 * y envía el token al backend de ICChocolate.
 */
export async function registerForPushNotifications() {
  try {
    if (!Device.isDevice) {
      console.warn('Push notifications solo funcionan en dispositivos físicos.');
      return null;
    }

    // Pedir permiso
    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;
    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      console.warn('Permiso de notificaciones denegado.');
      return null;
    }

    // Configurar canal en Android
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('sensor-alerts', {
        name: 'Alertas de sensor',
        importance: Notifications.AndroidImportance.HIGH,
        sound: 'default',
        vibrationPattern: [0, 250, 250, 250],
      });
    }

    // Intentar registrar push token remoto solo si no está en Expo Go o si está soportado
    let expoToken = null;
    try {
      const tokenData = await Notifications.getExpoPushTokenAsync().catch(() => null);
      if (tokenData?.data) {
        expoToken = tokenData.data;
        await registerExpoPushToken(expoToken).catch(() => {});
      }
    } catch {
      // En Expo Go Android SDK 53+, los push remotos se delegan a local notifications
    }
    return expoToken;
  } catch {
    return null;
  }
}

/**
 * Notificación local instantánea para anomalías de sensor o alertas de chocolate.
 */
export async function sendLocalNotification(title, body) {
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title,
        body,
        sound: 'default',
        vibrate: [0, 250, 250, 250],
      },
      trigger: null, // inmediato
    });
  } catch {
    // Silencioso
  }
}

/**
 * Agrega listeners para notificaciones recibidas y pulsadas.
 * Retorna función de limpieza.
 */
export function addNotificationListeners(onReceived, onTapped) {
  const subReceived = Notifications.addNotificationReceivedListener((notification) => {
    if (onReceived) onReceived(notification);
  });

  const subTapped = Notifications.addNotificationResponseReceivedListener((response) => {
    if (onTapped) onTapped(response);
  });

  return () => {
    subReceived.remove();
    subTapped.remove();
  };
}

