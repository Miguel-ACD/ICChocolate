import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, Image, Alert, StyleSheet,
  ScrollView, ActivityIndicator, TextInput, Modal
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import {
  uploadPhoto, fetchCatalog, fetchDrafts, createDraft,
  confirmDraft, cancelDraft, confirmPhotoGroup
} from '../api';

export default function CameraScreen({ navigation }) {
  // Modo activo: 'FOTO' | 'MANUAL' | 'CONVERTIR' | 'BORRADORES'
  const [activeTab, setActiveTab] = useState('FOTO');

  // Catálogo (presentaciones, ubicaciones, equivalencias, tipos)
  const [catalog, setCatalog] = useState({
    presentations: [],
    locations: [],
    equivalences: [],
    movement_types: [],
  });
  const [catalogLoading, setCatalogLoading] = useState(true);

  // Lista de borradores pendientes
  const [drafts, setDrafts] = useState([]);
  const [loadingDrafts, setLoadingDrafts] = useState(false);

  // ==========================================
  // ESTADO: MODO 1 (FOTO IA)
  // ==========================================
  const [photoUri, setPhotoUri] = useState(null);
  const [docKind, setDocKind] = useState('BOLETA'); // 'BOLETA' | 'ETIQUETA'
  const [analyzing, setAnalyzing] = useState(false);
  const [photoGroupData, setPhotoGroupData] = useState(null); // { id, group_id, extraction_items }
  const [photoType, setPhotoType] = useState('COMPRA'); // 'COMPRA' | 'VENTA'
  const [photoLocationId, setPhotoLocationId] = useState(null);
  const [photoRows, setPhotoRows] = useState([]); // [{ presentation_id, quantity }]
  const [submittingPhoto, setSubmittingPhoto] = useState(false);

  // ==========================================
  // ESTADO: MODO 2 (MANUAL)
  // ==========================================
  const [manualType, setManualType] = useState('COMPRA');
  const [manualPresId, setManualPresId] = useState(null);
  const [manualQty, setManualQty] = useState('1');
  const [manualSourceId, setManualSourceId] = useState(null);
  const [manualDestId, setManualDestId] = useState(null);
  const [manualReason, setManualReason] = useState('');
  const [submittingManual, setSubmittingManual] = useState(false);

  // ==========================================
  // ESTADO: MODO 3 (CONVERTIR)
  // ==========================================
  const [convEquivalenceId, setConvEquivalenceId] = useState(null);
  const [convMultiples, setConvMultiples] = useState('1');
  const [convLocationId, setConvLocationId] = useState(null);
  const [submittingConv, setSubmittingConv] = useState(false);

  // ==========================================
  // MODAL DE REVISIÓN Y CONFIRMACIÓN DE BORRADOR
  // ==========================================
  const [reviewModalVisible, setReviewModalVisible] = useState(false);
  const [draftToReview, setDraftToReview] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Cargar catálogo inicial y borradores
  const loadInitialData = useCallback(async () => {
    try {
      setCatalogLoading(true);
      const cat = await fetchCatalog();
      setCatalog(cat);
      if (cat.locations?.length > 0) {
        setPhotoLocationId(cat.locations[0].id);
        setManualSourceId(cat.locations[0].id);
        setConvLocationId(cat.locations[0].id);
      }
      if (cat.presentations?.length > 0) {
        setManualPresId(cat.presentations[0].id);
      }
      if (cat.equivalences?.length > 0) {
        setConvEquivalenceId(cat.equivalences[0].id);
      }
    } catch (e) {
      console.warn('Error al cargar catálogo:', e);
      Alert.alert('Error', 'No se pudo cargar el catálogo de productos.');
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  const loadDraftsList = useCallback(async () => {
    try {
      setLoadingDrafts(true);
      const res = await fetchDrafts();
      setDrafts(res.drafts || []);
    } catch (e) {
      console.warn('Error al cargar borradores:', e);
    } finally {
      setLoadingDrafts(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
    loadDraftsList();
  }, [loadInitialData, loadDraftsList]);

  // ==========================================
  // LÓGICA MODO 1: FOTO IA
  // ==========================================
  const openCamera = async () => {
    try {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permiso denegado', 'Permite el acceso a la cámara en los ajustes del celular.');
        return;
      }
      const res = await ImagePicker.launchCameraAsync({ quality: 0.8, allowsEditing: false });
      if (!res.canceled && res.assets?.length > 0) {
        setPhotoUri(res.assets[0].uri);
        setPhotoGroupData(null);
        setPhotoRows([]);
      }
    } catch (e) {
      console.warn('Error al abrir la cámara:', e);
      Alert.alert('Error', 'No se pudo activar la cámara.');
    }
  };

  const openGallery = async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permiso denegado', 'Permite el acceso a tu galería de fotos.');
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({ quality: 0.8, allowsEditing: false });
      if (!res.canceled && res.assets?.length > 0) {
        setPhotoUri(res.assets[0].uri);
        setPhotoGroupData(null);
        setPhotoRows([]);
      }
    } catch (e) {
      console.warn('Error al abrir galería:', e);
      Alert.alert('Error', 'No se pudo seleccionar la foto.');
    }
  };

  const analyzePhoto = async () => {
    if (!photoUri) return;
    setAnalyzing(true);
    try {
      const data = await uploadPhoto(photoUri, docKind);
      setPhotoGroupData(data);

      // Mapear items detectados por Gemini Vision con las presentaciones del catálogo
      const initialRows = [];
      if (data.extraction_items && Array.isArray(data.extraction_items)) {
        data.extraction_items.forEach((item) => {
          let matchedPres = catalog.presentations.find(
            (p) => p.code.toLowerCase() === (item.code || '').toLowerCase()
          );
          if (!matchedPres && item.presentation_id) {
            matchedPres = catalog.presentations.find((p) => p.id === Number(item.presentation_id));
          }
          if (matchedPres) {
            initialRows.push({
              presentation_id: matchedPres.id,
              quantity: String(item.quantity || 1),
            });
          }
        });
      }
      // Si no detectó ningún item o faltan, agregamos un renglón por defecto
      if (initialRows.length === 0 && catalog.presentations.length > 0) {
        initialRows.push({
          presentation_id: catalog.presentations[0].id,
          quantity: '1',
        });
      }
      setPhotoRows(initialRows);

      Alert.alert(
        '✨ Análisis IA completado',
        `Gemini Vision procesó el documento. Revisa los renglones propuestos antes de confirmar.`
      );
    } catch (e) {
      console.warn('Error al analizar foto:', e);
      Alert.alert('Aviso', 'Se subió la foto pero no se pudo completar el OCR. Puedes ingresar los datos manualmente.');
      if (catalog.presentations.length > 0) {
        setPhotoRows([{ presentation_id: catalog.presentations[0].id, quantity: '1' }]);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const addPhotoRow = () => {
    if (catalog.presentations.length === 0) return;
    setPhotoRows([...photoRows, { presentation_id: catalog.presentations[0].id, quantity: '1' }]);
  };

  const updatePhotoRow = (index, field, value) => {
    const updated = [...photoRows];
    updated[index][field] = value;
    setPhotoRows(updated);
  };

  const removePhotoRow = (index) => {
    if (photoRows.length <= 1) {
      Alert.alert('Aviso', 'Debe haber al menos un renglón de producto.');
      return;
    }
    setPhotoRows(photoRows.filter((_, i) => i !== index));
  };

  const handleConfirmPhotoMovement = async () => {
    if (!photoGroupData?.group_id) {
      Alert.alert('Falta análisis', 'Primero analiza la foto con IA antes de confirmar.');
      return;
    }
    if (!photoLocationId) {
      Alert.alert('Ubicación requerida', 'Selecciona la ubicación (Almacén o Display).');
      return;
    }

    const cleanedRows = photoRows.map((r) => ({
      presentation_id: Number(r.presentation_id),
      quantity: Number(r.quantity),
    })).filter((r) => r.presentation_id && r.quantity > 0);

    if (cleanedRows.length === 0) {
      Alert.alert('Renglones vacíos', 'Ingresa cantidades válidas mayores a 0.');
      return;
    }

    setSubmittingPhoto(true);
    try {
      const res = await confirmPhotoGroup({
        group_id: photoGroupData.group_id,
        type: photoType,
        location_id: photoLocationId,
        rows: cleanedRows,
      });

      Alert.alert('✅ Movimiento Exitoso', res.message || 'Movimiento con foto registrado e inventario actualizado.', [
        {
          text: 'Ver Historial',
          onPress: () => navigation.navigate('History'),
        },
        {
          text: 'Aceptar',
          onPress: () => {
            setPhotoUri(null);
            setPhotoGroupData(null);
            setPhotoRows([]);
          },
        },
      ]);
    } catch (e) {
      console.warn('Error al confirmar fotos:', e);
      const msg = e.response?.data?.error || 'No se pudo confirmar el movimiento con fotografías.';
      Alert.alert('Error', msg);
    } finally {
      setSubmittingPhoto(false);
    }
  };

  // ==========================================
  // LÓGICA MODO 2: MANUAL
  // ==========================================
  const handleSaveManualDraft = async () => {
    const qty = parseInt(manualQty, 10);
    if (!qty || qty <= 0) {
      Alert.alert('Cantidad inválida', 'Ingresa una cantidad mayor a 0.');
      return;
    }
    if (!manualPresId || !manualSourceId) {
      Alert.alert('Campos incompletos', 'Selecciona el producto y la ubicación.');
      return;
    }
    if (manualType === 'TRASLADO' && manualSourceId === manualDestId) {
      Alert.alert('Ubicación idéntica', 'El destino del traslado debe ser diferente al origen.');
      return;
    }
    if ((manualType === 'MERMA' || manualType === 'CONSUMO') && !manualReason.trim()) {
      Alert.alert('Motivo requerido', 'Para mermas o consumos es obligatorio ingresar el motivo.');
      return;
    }

    setSubmittingManual(true);
    try {
      const res = await createDraft({
        type: manualType,
        presentation_id: manualPresId,
        quantity: qty,
        source_id: manualSourceId,
        destination_id: manualType === 'TRASLADO' ? manualDestId : null,
        reason: manualReason.trim(),
      });

      Alert.alert(
        '📋 Borrador Guardado',
        'El movimiento se guardó como borrador. Puedes revisarlo ahora o confirmarlo más tarde.',
        [
          {
            text: 'Revisar y Confirmar Ahora',
            onPress: async () => {
              await loadDraftsList();
              setActiveTab('BORRADORES');
            },
          },
          {
            text: 'Guardar Otro',
            onPress: () => {
              setManualQty('1');
              setManualReason('');
              loadDraftsList();
            },
          },
        ]
      );
    } catch (e) {
      console.warn('Error al crear borrador:', e);
      const msg = e.response?.data?.error || 'No se pudo guardar el borrador.';
      Alert.alert('Error', msg);
    } finally {
      setSubmittingManual(false);
    }
  };

  // ==========================================
  // LÓGICA MODO 3: CONVERSIÓN
  // ==========================================
  const selectedEquivalence = catalog.equivalences?.find((e) => e.id === convEquivalenceId);
  const multipleCount = parseInt(convMultiples, 10) || 0;

  const handleSaveConversionDraft = async () => {
    if (!multipleCount || multipleCount <= 0) {
      Alert.alert('Múltiplos inválidos', 'Ingresa cuántas unidades deseas convertir (al menos 1).');
      return;
    }
    if (!convEquivalenceId || !convLocationId) {
      Alert.alert('Campos incompletos', 'Selecciona la equivalencia y la ubicación.');
      return;
    }

    setSubmittingConv(true);
    try {
      const res = await createDraft({
        type: 'CONVERSION',
        equivalence_id: convEquivalenceId,
        quantity: multipleCount,
        source_id: convLocationId,
      });

      Alert.alert(
        '🔄 Conversión en Borrador',
        'La conversión ha sido preparada. Revísala para verificar el impacto en el stock antes de aplicar.',
        [
          {
            text: 'Revisar y Confirmar',
            onPress: async () => {
              await loadDraftsList();
              setActiveTab('BORRADORES');
            },
          },
          {
            text: 'Aceptar',
            onPress: () => {
              setConvMultiples('1');
              loadDraftsList();
            },
          },
        ]
      );
    } catch (e) {
      console.warn('Error al crear conversión:', e);
      const msg = e.response?.data?.error || 'No se pudo preparar la conversión.';
      Alert.alert('Error', msg);
    } finally {
      setSubmittingConv(false);
    }
  };

  // ==========================================
  // LÓGICA MODO 4: BORRADORES PENDIENTES
  // ==========================================
  const handleOpenReview = (draft) => {
    setDraftToReview(draft);
    setReviewModalVisible(true);
  };

  const handleConfirmDraft = async (draft) => {
    setActionLoading(true);
    try {
      const res = await confirmDraft(draft.id, draft.version);
      setReviewModalVisible(false);
      setDraftToReview(null);
      await loadDraftsList();
      Alert.alert('🎉 Operación Exitosa', res.message || 'Movimiento confirmado en inventario.', [
        { text: 'Ver Historial', onPress: () => navigation.navigate('History') },
        { text: 'Aceptar' },
      ]);
    } catch (e) {
      console.warn('Error al confirmar borrador:', e);
      const msg = e.response?.data?.error || 'No se pudo confirmar el borrador.';
      Alert.alert('Error', msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelDraft = async (draft) => {
    Alert.alert(
      'Cancelar Borrador',
      '¿Deseas anular este borrador? No afectará el inventario.',
      [
        { text: 'No', style: 'cancel' },
        {
          text: 'Sí, Anular',
          style: 'destructive',
          onPress: async () => {
            setActionLoading(true);
            try {
              await cancelDraft(draft.id, draft.version);
              setReviewModalVisible(false);
              setDraftToReview(null);
              await loadDraftsList();
              Alert.alert('Borrador Cancelado', 'El borrador fue anulado correctamente.');
            } catch (e) {
              const msg = e.response?.data?.error || 'No se pudo cancelar el borrador.';
              Alert.alert('Error', msg);
            } finally {
              setActionLoading(false);
            }
          },
        },
      ]
    );
  };

  if (catalogLoading) {
    return (
      <View style={styles.loadingCenter}>
        <ActivityIndicator size="large" color="#4a2c2a" />
        <Text style={styles.loadingText}>Cargando catálogo y operaciones…</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Barra de pestañas superiores */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === 'FOTO' && styles.tabBtnActive]}
          onPress={() => setActiveTab('FOTO')}
        >
          <Text style={styles.tabIcon}>📸</Text>
          <Text style={[styles.tabLabel, activeTab === 'FOTO' && styles.tabLabelActive]}>
            Con Foto
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabBtn, activeTab === 'MANUAL' && styles.tabBtnActive]}
          onPress={() => setActiveTab('MANUAL')}
        >
          <Text style={styles.tabIcon}>✍️</Text>
          <Text style={[styles.tabLabel, activeTab === 'MANUAL' && styles.tabLabelActive]}>
            Manual
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabBtn, activeTab === 'CONVERTIR' && styles.tabBtnActive]}
          onPress={() => setActiveTab('CONVERTIR')}
        >
          <Text style={styles.tabIcon}>🔄</Text>
          <Text style={[styles.tabLabel, activeTab === 'CONVERTIR' && styles.tabLabelActive]}>
            Convertir
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabBtn, activeTab === 'BORRADORES' && styles.tabBtnActive]}
          onPress={() => {
            setActiveTab('BORRADORES');
            loadDraftsList();
          }}
        >
          <Text style={styles.tabIcon}>📋</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Text style={[styles.tabLabel, activeTab === 'BORRADORES' && styles.tabLabelActive]}>
              Borradores
            </Text>
            {drafts.length > 0 && (
              <View style={styles.badgeCount}>
                <Text style={styles.badgeCountText}>{drafts.length}</Text>
              </View>
            )}
          </View>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* ======================================================= */}
        {/* TAB 1: REGISTRO CON FOTO (GEMINI VISION)                */}
        {/* ======================================================= */}
        {activeTab === 'FOTO' && (
          <View>
            <Text style={styles.headerTitle}>Registro con Fotografías e IA</Text>
            <Text style={styles.headerSubtitle}>
              Fotografía boletas de compra/venta o etiquetas de lote. Gemini Vision extraerá automáticamente los productos para su revisión.
            </Text>

            {/* Selector de Tipo de Documento */}
            <View style={styles.segmentedSelector}>
              <TouchableOpacity
                style={[styles.segBtn, docKind === 'BOLETA' && styles.segBtnActive]}
                onPress={() => setDocKind('BOLETA')}
              >
                <Text style={[styles.segBtnText, docKind === 'BOLETA' && styles.segBtnTextActive]}>
                  🧾 Boleta / Factura
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.segBtn, docKind === 'ETIQUETA' && styles.segBtnActive]}
                onPress={() => setDocKind('ETIQUETA')}
              >
                <Text style={[styles.segBtnText, docKind === 'ETIQUETA' && styles.segBtnTextActive]}>
                  🏷️ Etiqueta de Chocolate
                </Text>
              </TouchableOpacity>
            </View>

            {/* Opciones de captura */}
            {!photoUri ? (
              <View style={styles.captureBox}>
                <TouchableOpacity style={styles.btnCameraBig} onPress={openCamera}>
                  <Text style={styles.btnCameraBigEmoji}>📸</Text>
                  <Text style={styles.btnCameraBigTitle}>Tomar Foto con Cámara</Text>
                  <Text style={styles.btnCameraBigSub}>Apertura directa del sensor</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.btnGalleryBar} onPress={openGallery}>
                  <Text style={styles.btnGalleryBarText}>🖼️ Seleccionar desde la Galería</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.previewCard}>
                <Image source={{ uri: photoUri }} style={styles.previewImg} resizeMode="cover" />

                <View style={styles.previewActionRow}>
                  <TouchableOpacity
                    style={styles.btnSecondary}
                    onPress={() => {
                      setPhotoUri(null);
                      setPhotoGroupData(null);
                      setPhotoRows([]);
                    }}
                    disabled={analyzing || submittingPhoto}
                  >
                    <Text style={styles.btnSecondaryText}>🔄 Cambiar Foto</Text>
                  </TouchableOpacity>

                  {!photoGroupData ? (
                    <TouchableOpacity
                      style={[styles.btnPrimary, analyzing && styles.btnDisabled]}
                      onPress={analyzePhoto}
                      disabled={analyzing}
                    >
                      {analyzing ? (
                        <ActivityIndicator color="#fff" size="small" />
                      ) : (
                        <Text style={styles.btnPrimaryText}>⚡ Analizar con IA</Text>
                      )}
                    </TouchableOpacity>
                  ) : (
                    <View style={styles.analyzedBadge}>
                      <Text style={styles.analyzedBadgeText}>✅ Analizado por Gemini</Text>
                    </View>
                  )}
                </View>
              </View>
            )}

            {/* Formulario de revisión y corrección de datos tras OCR */}
            {photoGroupData && (
              <View style={styles.reviewSection}>
                <Text style={styles.sectionTitle}>Revisar y Corregir Renglones Detectados</Text>
                <Text style={styles.sectionHint}>
                  Asegúrate de que los códigos de presentación y cantidades coincidan con el documento físico.
                </Text>

                {/* Tipo de movimiento y ubicación */}
                <View style={styles.inputGroup}>
                  <Text style={styles.inputLabel}>Tipo de Operación con Foto:</Text>
                  <View style={styles.segmentedSelector}>
                    <TouchableOpacity
                      style={[styles.segBtn, photoType === 'COMPRA' && styles.segBtnActive]}
                      onPress={() => setPhotoType('COMPRA')}
                    >
                      <Text style={[styles.segBtnText, photoType === 'COMPRA' && styles.segBtnTextActive]}>
                        🛒 Compra / Ingreso
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.segBtn, photoType === 'VENTA' && styles.segBtnActive]}
                      onPress={() => setPhotoType('VENTA')}
                    >
                      <Text style={[styles.segBtnText, photoType === 'VENTA' && styles.segBtnTextActive]}>
                        💰 Venta / Salida
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>

                <View style={styles.inputGroup}>
                  <Text style={styles.inputLabel}>Ubicación Destino / Origen:</Text>
                  <View style={styles.pillRow}>
                    {(catalog.locations || []).map((loc) => {
                      const sel = photoLocationId === loc.id;
                      return (
                        <TouchableOpacity
                          key={loc.id}
                          style={[styles.pill, sel && styles.pillActive]}
                          onPress={() => setPhotoLocationId(loc.id)}
                        >
                          <Text style={[styles.pillText, sel && styles.pillTextActive]}>
                            {loc.name}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>

                {/* Lista de renglones editables */}
                <Text style={[styles.inputLabel, { marginTop: 10 }]}>Renglones de Productos:</Text>
                {photoRows.map((row, idx) => (
                  <View key={idx} style={styles.rowItemCard}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowItemNumber}>Ítem #{idx + 1}</Text>
                      {/* Selector de Presentación */}
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginVertical: 4 }}>
                        {(catalog.presentations || []).map((pres) => {
                          const isPresSel = Number(row.presentation_id) === pres.id;
                          return (
                            <TouchableOpacity
                              key={pres.id}
                              style={[styles.miniPresPill, isPresSel && styles.miniPresPillActive]}
                              onPress={() => updatePhotoRow(idx, 'presentation_id', pres.id)}
                            >
                              <Text style={[styles.miniPresCode, isPresSel && styles.miniPresTextActive]}>
                                {pres.code}
                              </Text>
                              <Text style={[styles.miniPresName, isPresSel && styles.miniPresTextActive]}>
                                {pres.name}
                              </Text>
                            </TouchableOpacity>
                          );
                        })}
                      </ScrollView>
                    </View>

                    {/* Cantidad y botón eliminar */}
                    <View style={styles.qtyRowAction}>
                      <View style={styles.qtyBox}>
                        <Text style={styles.qtyBoxLabel}>Cant:</Text>
                        <TextInput
                          style={styles.qtyInput}
                          keyboardType="numeric"
                          value={String(row.quantity)}
                          onChangeText={(v) => updatePhotoRow(idx, 'quantity', v)}
                        />
                      </View>
                      <TouchableOpacity onPress={() => removePhotoRow(idx)} style={styles.btnRowRemove}>
                        <Text style={styles.btnRowRemoveText}>🗑️</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}

                <TouchableOpacity style={styles.btnAddRow} onPress={addPhotoRow}>
                  <Text style={styles.btnAddRowText}>➕ Agregar otro renglón</Text>
                </TouchableOpacity>

                {/* Botón de Confirmación Definitiva */}
                <TouchableOpacity
                  style={[styles.btnConfirmBig, submittingPhoto && styles.btnDisabled]}
                  onPress={handleConfirmPhotoMovement}
                  disabled={submittingPhoto}
                >
                  {submittingPhoto ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.btnConfirmBigText}>
                      ✓ Confirmar y Actualizar Inventario
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* ======================================================= */}
        {/* TAB 2: REGISTRO MANUAL DE MOVIMIENTO                    */}
        {/* ======================================================= */}
        {activeTab === 'MANUAL' && (
          <View>
            <Text style={styles.headerTitle}>Registrar Movimiento Manual</Text>
            <Text style={styles.headerSubtitle}>
              Ingresa compras, ventas, traslados, mermas o ajustes directamente. Se guardará como borrador para tu revisión.
            </Text>

            {/* Tipo de Movimiento */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Tipo de Movimiento:</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pillRow}>
                {(catalog.movement_types || []).map((t) => {
                  const sel = manualType === t.code;
                  return (
                    <TouchableOpacity
                      key={t.code}
                      style={[styles.pill, sel && styles.pillActive]}
                      onPress={() => setManualType(t.code)}
                    >
                      <Text style={[styles.pillText, sel && styles.pillTextActive]}>
                        {t.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </View>

            {/* Presentación */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Presentación de Chocolate:</Text>
              {(catalog.presentations || []).map((p) => {
                const sel = manualPresId === p.id;
                return (
                  <TouchableOpacity
                    key={p.id}
                    style={[styles.presChoiceCard, sel && styles.presChoiceCardActive]}
                    onPress={() => setManualPresId(p.id)}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.presChoiceCode, sel && styles.presChoiceCodeActive]}>
                        🍫 {p.code}
                      </Text>
                      <Text style={[styles.presChoiceName, sel && styles.presChoiceNameActive]}>
                        {p.product_name} · {p.name}
                      </Text>
                    </View>
                    {sel && <Text style={styles.checkMark}>✓</Text>}
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Cantidad */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Cantidad (unidades):</Text>
              <View style={styles.manualQtyRow}>
                <TextInput
                  style={styles.manualQtyInput}
                  keyboardType="numeric"
                  value={manualQty}
                  onChangeText={setManualQty}
                />
                <View style={styles.quickQtyChips}>
                  {['1', '5', '10', '24'].map((val) => (
                    <TouchableOpacity
                      key={val}
                      style={styles.chipQuick}
                      onPress={() => setManualQty(val)}
                    >
                      <Text style={styles.chipQuickText}>+{val}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>

            {/* Ubicación Origen */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Ubicación {manualType === 'TRASLADO' ? 'de Origen' : 'del Stock'}:</Text>
              <View style={styles.pillRow}>
                {(catalog.locations || []).map((loc) => {
                  const sel = manualSourceId === loc.id;
                  return (
                    <TouchableOpacity
                      key={loc.id}
                      style={[styles.pill, sel && styles.pillActive]}
                      onPress={() => setManualSourceId(loc.id)}
                    >
                      <Text style={[styles.pillText, sel && styles.pillTextActive]}>
                        📍 {loc.name}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {/* Ubicación Destino (si es TRASLADO) */}
            {manualType === 'TRASLADO' && (
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Ubicación de Destino:</Text>
                <View style={styles.pillRow}>
                  {(catalog.locations || []).map((loc) => {
                    const sel = manualDestId === loc.id;
                    return (
                      <TouchableOpacity
                        key={loc.id}
                        style={[styles.pill, sel && styles.pillActive]}
                        onPress={() => setManualDestId(loc.id)}
                      >
                        <Text style={[styles.pillText, sel && styles.pillTextActive]}>
                          🎯 {loc.name}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            )}

            {/* Motivo */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>
                Motivo / Razón {['MERMA', 'CONSUMO'].includes(manualType) ? '(Obligatorio)' : '(Opcional)'}:
              </Text>
              <TextInput
                style={styles.reasonInput}
                placeholder="Ej. Ingreso por compra a proveedor, merma por empaque dañado..."
                placeholderTextColor="#9e8b7c"
                value={manualReason}
                onChangeText={setManualReason}
                multiline
                numberOfLines={2}
              />
            </View>

            {/* Botón de Guardar Borrador */}
            <TouchableOpacity
              style={[styles.btnPrimaryBig, submittingManual && styles.btnDisabled]}
              onPress={handleSaveManualDraft}
              disabled={submittingManual}
            >
              {submittingManual ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.btnPrimaryBigText}>
                  💾 Guardar y Revisar Borrador
                </Text>
              )}
            </TouchableOpacity>
          </View>
        )}

        {/* ======================================================= */}
        {/* TAB 3: CONVERTIR PRESENTACIONES (EQUIVALENCIAS)         */}
        {/* ======================================================= */}
        {activeTab === 'CONVERTIR' && (
          <View>
            <Text style={styles.headerTitle}>Convertir Presentaciones</Text>
            <Text style={styles.headerSubtitle}>
              Transforma cajas a barras o sacos a bolsas según las reglas de equivalencia activas.
            </Text>

            {/* Selector de Equivalencia */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Selecciona la Regla de Conversión:</Text>
              {(catalog.equivalences || []).map((eq) => {
                const sel = convEquivalenceId === eq.id;
                return (
                  <TouchableOpacity
                    key={eq.id}
                    style={[styles.equivCard, sel && styles.equivCardActive]}
                    onPress={() => setConvEquivalenceId(eq.id)}
                  >
                    <View style={styles.equivHeader}>
                      <Text style={[styles.equivCode, sel && styles.equivCodeActive]}>
                        📦 {eq.source_code} ({eq.source_units} ud) ➔ 🍫 {eq.target_code} ({eq.target_units} uds)
                      </Text>
                      {sel && <Text style={styles.checkMark}>✓</Text>}
                    </View>
                    <Text style={styles.equivSub}>
                      Origen: {eq.source_name} {'\n'}Destino: {eq.target_name}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Múltiplos */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Múltiplos a Convertir:</Text>
              <View style={styles.manualQtyRow}>
                <TextInput
                  style={styles.manualQtyInput}
                  keyboardType="numeric"
                  value={convMultiples}
                  onChangeText={setConvMultiples}
                />
                <View style={styles.quickQtyChips}>
                  {['1', '2', '5', '10'].map((val) => (
                    <TouchableOpacity
                      key={val}
                      style={styles.chipQuick}
                      onPress={() => setConvMultiples(val)}
                    >
                      <Text style={styles.chipQuickText}>{val}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>

            {/* Ubicación */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Ubicación donde se realiza la conversión:</Text>
              <View style={styles.pillRow}>
                {(catalog.locations || []).map((loc) => {
                  const sel = convLocationId === loc.id;
                  return (
                    <TouchableOpacity
                      key={loc.id}
                      style={[styles.pill, sel && styles.pillActive]}
                      onPress={() => setConvLocationId(loc.id)}
                    >
                      <Text style={[styles.pillText, sel && styles.pillTextActive]}>
                        📍 {loc.name}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {/* Previsualización del Impacto de Conversión */}
            {selectedEquivalence && multipleCount > 0 && (
              <View style={styles.previewCalcCard}>
                <Text style={styles.previewCalcTitle}>📊 Impacto en el Inventario:</Text>
                <View style={styles.calcRow}>
                  <Text style={styles.calcNegative}>
                    - {selectedEquivalence.source_units * multipleCount} {selectedEquivalence.source_code}
                  </Text>
                  <Text style={styles.calcArrow}>➔</Text>
                  <Text style={styles.calcPositive}>
                    + {selectedEquivalence.target_units * multipleCount} {selectedEquivalence.target_code}
                  </Text>
                </View>
                <Text style={styles.calcNote}>
                  La operación se realiza en la misma ubicación seleccionada.
                </Text>
              </View>
            )}

            {/* Botón de Preparar Conversión */}
            <TouchableOpacity
              style={[styles.btnPrimaryBig, submittingConv && styles.btnDisabled]}
              onPress={handleSaveConversionDraft}
              disabled={submittingConv}
            >
              {submittingConv ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.btnPrimaryBigText}>
                  🔄 Preparar y Revisar Conversión
                </Text>
              )}
            </TouchableOpacity>
          </View>
        )}

        {/* ======================================================= */}
        {/* TAB 4: BORRADORES PENDIENTES (REVISIÓN Y CONFIRMACIÓN)  */}
        {/* ======================================================= */}
        {activeTab === 'BORRADORES' && (
          <View>
            <View style={styles.draftsTopRow}>
              <View>
                <Text style={styles.headerTitle}>Borradores Pendientes</Text>
                <Text style={styles.headerSubtitle}>
                  Revisa, confirma o cancela operaciones antes de que alteren el inventario.
                </Text>
              </View>
              <TouchableOpacity onPress={loadDraftsList} style={styles.btnSmallRefresh}>
                <Text style={styles.btnSmallRefreshText}>🔄</Text>
              </TouchableOpacity>
            </View>

            {loadingDrafts ? (
              <ActivityIndicator color="#4a2c2a" style={{ marginTop: 24 }} />
            ) : drafts.length === 0 ? (
              <View style={styles.emptyDraftsBox}>
                <Text style={styles.emptyDraftsEmoji}>✨</Text>
                <Text style={styles.emptyDraftsTitle}>No hay borradores pendientes</Text>
                <Text style={styles.emptyDraftsSub}>
                  Todos los movimientos y conversiones han sido confirmados o cancelados.
                </Text>
              </View>
            ) : (
              drafts.map((draft) => (
                <View key={draft.id} style={styles.draftCard}>
                  <View style={styles.draftCardHeader}>
                    <View style={styles.draftBadge}>
                      <Text style={styles.draftBadgeText}>
                        {draft.type_label || draft.type}
                      </Text>
                    </View>
                    <Text style={styles.draftVersion}>v{draft.version}</Text>
                  </View>

                  {draft.type === 'CONVERSION' ? (
                    <Text style={styles.draftDetailText}>
                      🔄 {draft.equivalence_label} ({draft.quantity} múltiplos en {draft.source_name})
                    </Text>
                  ) : (
                    <Text style={styles.draftDetailText}>
                      📦 {draft.quantity} uds de {draft.presentation_name || draft.presentation_code}
                      {'\n'}📍 En: {draft.source_name}
                      {draft.destination_name ? ` ➔ ${draft.destination_name}` : ''}
                    </Text>
                  )}

                  {draft.reason ? (
                    <Text style={styles.draftReason}>Motivo: "{draft.reason}"</Text>
                  ) : null}

                  <Text style={styles.draftAuthor}>
                    Por: {draft.created_by_alias}
                  </Text>

                  {/* Botones de acción del borrador */}
                  <View style={styles.draftActionsRow}>
                    <TouchableOpacity
                      style={styles.btnDraftReview}
                      onPress={() => handleOpenReview(draft)}
                    >
                      <Text style={styles.btnDraftReviewText}>👁️ Revisar Detalle</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={styles.btnDraftConfirm}
                      onPress={() => handleConfirmDraft(draft)}
                    >
                      <Text style={styles.btnDraftConfirmText}>✓ Confirmar</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={styles.btnDraftCancel}
                      onPress={() => handleCancelDraft(draft)}
                    >
                      <Text style={styles.btnDraftCancelText}>✕</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>

      {/* ======================================================= */}
      {/* MODAL DE REVISIÓN DETALLADA DE BORRADOR                */}
      {/* ======================================================= */}
      <Modal
        visible={reviewModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setReviewModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Revisión de Movimiento</Text>
            <Text style={styles.modalSub}>
              Verifica los datos antes de que se apliquen al stock real de la tienda.
            </Text>

            {draftToReview && (
              <View style={styles.modalDetails}>
                <View style={styles.modalRow}>
                  <Text style={styles.modalLabel}>Tipo de Operación:</Text>
                  <Text style={styles.modalValue}>{draftToReview.type_label || draftToReview.type}</Text>
                </View>
                <View style={styles.modalRow}>
                  <Text style={styles.modalLabel}>Ubicación:</Text>
                  <Text style={styles.modalValue}>
                    {draftToReview.source_name}
                    {draftToReview.destination_name ? ` ➔ ${draftToReview.destination_name}` : ''}
                  </Text>
                </View>
                {draftToReview.type === 'CONVERSION' ? (
                  <View style={styles.modalRow}>
                    <Text style={styles.modalLabel}>Equivalencia:</Text>
                    <Text style={styles.modalValue}>{draftToReview.equivalence_label}</Text>
                  </View>
                ) : (
                  <View style={styles.modalRow}>
                    <Text style={styles.modalLabel}>Presentación:</Text>
                    <Text style={styles.modalValue}>{draftToReview.presentation_name}</Text>
                  </View>
                )}
                <View style={styles.modalRow}>
                  <Text style={styles.modalLabel}>Cantidad:</Text>
                  <Text style={[styles.modalValue, { fontWeight: 'bold', color: '#2e7d32' }]}>
                    {draftToReview.quantity} uds
                  </Text>
                </View>
                {draftToReview.reason ? (
                  <View style={styles.modalRow}>
                    <Text style={styles.modalLabel}>Motivo:</Text>
                    <Text style={styles.modalValue}>"{draftToReview.reason}"</Text>
                  </View>
                ) : null}
                <View style={styles.modalRow}>
                  <Text style={styles.modalLabel}>Registrado por:</Text>
                  <Text style={styles.modalValue}>{draftToReview.created_by_alias}</Text>
                </View>
              </View>
            )}

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalBtnCancel}
                onPress={() => setReviewModalVisible(false)}
                disabled={actionLoading}
              >
                <Text style={styles.modalBtnCancelText}>Volver</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.modalBtnConfirm}
                onPress={() => draftToReview && handleConfirmDraft(draftToReview)}
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.modalBtnConfirmText}>✓ Confirmar Ahora</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  loadingCenter: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fdf6ec' },
  loadingText: { marginTop: 12, fontSize: 14, color: '#4a2c2a' },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#ede0d0',
    paddingVertical: 6,
  },
  tabBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 6,
    borderRadius: 8,
    marginHorizontal: 4,
  },
  tabBtnActive: {
    backgroundColor: '#f5eee6',
  },
  tabIcon: { fontSize: 18 },
  tabLabel: { fontSize: 11, color: '#8c766b', marginTop: 2, fontWeight: '600' },
  tabLabelActive: { color: '#4a2c2a', fontWeight: 'bold' },
  badgeCount: {
    backgroundColor: '#c62828',
    borderRadius: 9,
    paddingHorizontal: 5,
    paddingVertical: 1,
    marginLeft: 3,
  },
  badgeCountText: { color: '#fff', fontSize: 10, fontWeight: 'bold' },
  scrollContent: { padding: 16, paddingBottom: 40 },
  headerTitle: { fontSize: 19, fontWeight: 'bold', color: '#4a2c2a', marginBottom: 4 },
  headerSubtitle: { fontSize: 13, color: '#7a6658', marginBottom: 16, lineHeight: 18 },
  segmentedSelector: {
    flexDirection: 'row',
    backgroundColor: '#f5eee6',
    borderRadius: 10,
    padding: 3,
    marginBottom: 14,
  },
  segBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 8,
  },
  segBtnActive: {
    backgroundColor: '#4a2c2a',
  },
  segBtnText: { fontSize: 13, fontWeight: '600', color: '#6d5a4d' },
  segBtnTextActive: { color: '#fff' },
  captureBox: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 16,
  },
  btnCameraBig: {
    width: '100%',
    backgroundColor: '#4a2c2a',
    paddingVertical: 18,
    borderRadius: 12,
    alignItems: 'center',
    marginBottom: 12,
  },
  btnCameraBigEmoji: { fontSize: 32, marginBottom: 4 },
  btnCameraBigTitle: { fontSize: 16, fontWeight: 'bold', color: '#fff' },
  btnCameraBigSub: { fontSize: 12, color: '#f2e8dc', marginTop: 2 },
  btnGalleryBar: {
    width: '100%',
    backgroundColor: '#f5eee6',
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
  },
  btnGalleryBarText: { fontSize: 14, fontWeight: '600', color: '#4a2c2a' },
  previewCard: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 16,
  },
  previewImg: { width: '100%', height: 220, borderRadius: 10 },
  previewActionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 10,
  },
  btnSecondary: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#f5eee6',
  },
  btnSecondaryText: { fontSize: 13, color: '#4a2c2a', fontWeight: '600' },
  btnPrimary: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#4a2c2a',
  },
  btnPrimaryText: { fontSize: 13, color: '#fff', fontWeight: 'bold' },
  analyzedBadge: {
    backgroundColor: '#e8f5e9',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  analyzedBadgeText: { color: '#2e7d32', fontSize: 12, fontWeight: 'bold' },
  reviewSection: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 20,
  },
  sectionTitle: { fontSize: 15, fontWeight: 'bold', color: '#4a2c2a', marginBottom: 2 },
  sectionHint: { fontSize: 12, color: '#8c766b', marginBottom: 12 },
  inputGroup: { marginBottom: 14 },
  inputLabel: { fontSize: 13, fontWeight: 'bold', color: '#4a2c2a', marginBottom: 6 },
  pillRow: { flexDirection: 'row', gap: 8 },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 18,
    backgroundColor: '#f5eee6',
    borderWidth: 1,
    borderColor: '#e2d3c2',
    marginRight: 6,
  },
  pillActive: { backgroundColor: '#4a2c2a', borderColor: '#4a2c2a' },
  pillText: { fontSize: 12, fontWeight: '600', color: '#6d5a4d' },
  pillTextActive: { color: '#fff' },
  rowItemCard: {
    backgroundColor: '#faf6f0',
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#ede4d8',
  },
  rowItemNumber: { fontSize: 11, fontWeight: 'bold', color: '#8c766b' },
  miniPresPill: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#dfcfbe',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    marginRight: 6,
  },
  miniPresPillActive: { backgroundColor: '#4a2c2a', borderColor: '#4a2c2a' },
  miniPresCode: { fontSize: 11, fontWeight: 'bold', color: '#4a2c2a' },
  miniPresName: { fontSize: 10, color: '#8c766b' },
  miniPresTextActive: { color: '#fff' },
  qtyRowAction: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 6,
  },
  qtyBox: { flexDirection: 'row', alignItems: 'center' },
  qtyBoxLabel: { fontSize: 12, color: '#6d5a4d', marginRight: 6 },
  qtyInput: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#dfcfbe',
    borderRadius: 6,
    width: 60,
    height: 34,
    textAlign: 'center',
    fontSize: 14,
    fontWeight: 'bold',
    color: '#4a2c2a',
  },
  btnRowRemove: { padding: 6 },
  btnRowRemoveText: { fontSize: 16 },
  btnAddRow: {
    backgroundColor: '#f5eee6',
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 14,
  },
  btnAddRowText: { fontSize: 13, fontWeight: 'bold', color: '#4a2c2a' },
  btnConfirmBig: {
    backgroundColor: '#2e7d32',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  btnConfirmBigText: { color: '#fff', fontSize: 15, fontWeight: 'bold' },
  presChoiceCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 6,
  },
  presChoiceCardActive: { borderColor: '#4a2c2a', backgroundColor: '#fcf7f1' },
  presChoiceCode: { fontSize: 14, fontWeight: 'bold', color: '#4a2c2a' },
  presChoiceCodeActive: { color: '#4a2c2a' },
  presChoiceName: { fontSize: 12, color: '#8c766b', marginTop: 1 },
  presChoiceNameActive: { color: '#6d5a4d' },
  checkMark: { fontSize: 16, color: '#2e7d32', fontWeight: 'bold' },
  manualQtyRow: { flexDirection: 'row', alignItems: 'center' },
  manualQtyInput: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ebdccb',
    borderRadius: 8,
    width: 80,
    height: 42,
    textAlign: 'center',
    fontSize: 18,
    fontWeight: 'bold',
    color: '#4a2c2a',
    marginRight: 12,
  },
  quickQtyChips: { flexDirection: 'row', gap: 6 },
  chipQuick: {
    backgroundColor: '#f5eee6',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
  },
  chipQuickText: { fontSize: 13, fontWeight: 'bold', color: '#4a2c2a' },
  reasonInput: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ebdccb',
    borderRadius: 8,
    padding: 10,
    fontSize: 13,
    color: '#4a2c2a',
  },
  btnPrimaryBig: {
    backgroundColor: '#4a2c2a',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  btnPrimaryBigText: { color: '#fff', fontSize: 15, fontWeight: 'bold' },
  equivCard: {
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 8,
  },
  equivCardActive: { borderColor: '#4a2c2a', backgroundColor: '#fcf7f1' },
  equivHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  equivCode: { fontSize: 13, fontWeight: 'bold', color: '#4a2c2a' },
  equivCodeActive: { color: '#4a2c2a' },
  equivSub: { fontSize: 11, color: '#8c766b', marginTop: 4 },
  previewCalcCard: {
    backgroundColor: '#e8f5e9',
    borderRadius: 10,
    padding: 12,
    marginVertical: 10,
    borderWidth: 1,
    borderColor: '#c8e6c9',
  },
  previewCalcTitle: { fontSize: 12, fontWeight: 'bold', color: '#2e7d32', marginBottom: 4 },
  calcRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', marginVertical: 4 },
  calcNegative: { fontSize: 14, fontWeight: 'bold', color: '#c62828' },
  calcArrow: { fontSize: 16, color: '#2e7d32' },
  calcPositive: { fontSize: 14, fontWeight: 'bold', color: '#2e7d32' },
  calcNote: { fontSize: 11, color: '#558b2f', textAlign: 'center', marginTop: 2 },
  draftsTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  btnSmallRefresh: { padding: 8 },
  btnSmallRefreshText: { fontSize: 18 },
  emptyDraftsBox: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginTop: 20,
  },
  emptyDraftsEmoji: { fontSize: 36, marginBottom: 8 },
  emptyDraftsTitle: { fontSize: 15, fontWeight: 'bold', color: '#4a2c2a' },
  emptyDraftsSub: { fontSize: 12, color: '#8c766b', textAlign: 'center', marginTop: 4 },
  draftCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 10,
  },
  draftCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  draftBadge: { backgroundColor: '#f5eee6', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  draftBadgeText: { fontSize: 11, fontWeight: 'bold', color: '#4a2c2a' },
  draftVersion: { fontSize: 11, color: '#8c766b', fontWeight: 'bold' },
  draftDetailText: { fontSize: 13, fontWeight: '600', color: '#4a2c2a', lineHeight: 18 },
  draftReason: { fontSize: 12, fontStyle: 'italic', color: '#7a6658', marginTop: 4 },
  draftAuthor: { fontSize: 11, color: '#8c766b', marginTop: 4 },
  draftActionsRow: { flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 10 },
  btnDraftReview: {
    backgroundColor: '#f5eee6',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  btnDraftReviewText: { fontSize: 12, fontWeight: '600', color: '#4a2c2a' },
  btnDraftConfirm: {
    backgroundColor: '#2e7d32',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  btnDraftConfirmText: { fontSize: 12, fontWeight: 'bold', color: '#fff' },
  btnDraftCancel: {
    backgroundColor: '#ffebee',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  btnDraftCancelText: { fontSize: 12, fontWeight: 'bold', color: '#c62828' },
  btnDisabled: { opacity: 0.6 },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    maxWidth: 400,
  },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#4a2c2a' },
  modalSub: { fontSize: 12, color: '#7a6658', marginTop: 2, marginBottom: 14 },
  modalDetails: {
    backgroundColor: '#fbf8f4',
    padding: 12,
    borderRadius: 10,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#ede4d8',
  },
  modalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#f2eae1',
  },
  modalLabel: { fontSize: 12, color: '#6d5a4d' },
  modalValue: { fontSize: 12, fontWeight: '600', color: '#4a2c2a', flex: 1, textAlign: 'right' },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 10 },
  modalBtnCancel: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8, backgroundColor: '#f5eee6' },
  modalBtnCancelText: { fontSize: 13, fontWeight: '600', color: '#4a2c2a' },
  modalBtnConfirm: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8, backgroundColor: '#2e7d32' },
  modalBtnConfirmText: { fontSize: 13, fontWeight: 'bold', color: '#fff' },
});
