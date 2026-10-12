"""Domain service for structured Labor Model instances."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import fitz
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from payroll_core import ALLOWED_STORAGE_DIR, audit, safe_join_under_storage, utc_now


def _field(key: str, label: str, marker: str, source: Optional[str] = None, required: bool = True, input_type: str = "text", options: Optional[list[str]] = None) -> dict[str, Any]:
    field = {"key": key, "label": label, "marker": marker, "required": required, "input_type": input_type}
    if source:
        field["source"] = source
    if options:
        field["options"] = options
    return field


MODEL_CATALOG = {
    "TLG-INT-001": {
        "code": "TLG-INT-001", "category": "Abandono de trabajo",
        "model_label": "Modelo N° 1",
        "title": "Intimación al Trabajador (Ausencia / Presentación a Trabajar)",
        "description": "Intimación al trabajador por ausencia y presentación a trabajar.",
        "version": "1.1", "template_path": "Modelos Laborales/Plantilla Telegrama de Intimación MyManageRH (7).pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL / DNI]", "employee.cuil_or_dni"),
            _field("empleado.domicilio_completo", "Domicilio del Trabajador", "[Domicilio del Trabajador]", "employee.address"),
            _field("empresa.razon_social", "Razón Social de la Empresa", "[Razón Social de la Empresa]", "organization.name"),
            _field("incidencia.fecha_inicio_ausencia", "Fecha de Inicio de Ausencia", "[Fecha Inicio Ausencia]", input_type="date"),
        ],
    },
    "TLG-RRL-002": {
        "code": "TLG-RRL-002", "category": "Abandono de trabajo", "model_label": "Modelo N° 2",
        "title": "Notificación de Despacho por Abandono de Trabajo",
        "description": "Notificación de despacho por abandono de trabajo.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Telegrama de Ruptura Laboral MyManageRH (2).pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL/DNI]", "employee.cuil_or_dni"),
            _field("empleado.domicilio_completo", "Domicilio del Trabajador", "[Domicilio del Trabajador]", "employee.address"),
            _field("empresa.razon_social", "Razón Social de la Empresa", "[Razón Social de la Empresa]", "organization.name"),
            _field("empresa.cuit", "CUIT de la Empresa", "[CUIT Empresa]", "organization.cuit"),
            _field("telegrama.previo_numero", "Número del Telegrama Previo", "[Telegrama Previo N°]"),
        ],
    },
    "ATD-003": {
        "code": "ATD-003", "category": "DECLARACIONES", "model_label": "Formulario Estándar",
        "title": "Afiliación y Declaración Jurada del Trabajador",
        "description": "Formulario de afiliación y declaración jurada del trabajador.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Declaracion Jurada Afiliacion MyManageRH.pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL/DNI]", "employee.cuil_or_dni"),
            _field("empleado.domicilio_completo", "Domicilio del Trabajador", "[Domicilio del Trabajador]", "employee.address"),
            _field("empresa.razon_social", "Razón Social de la Empresa", "[Razón Social de la Empresa]", "organization.name"),
            _field("empresa.cuit", "CUIT de la Empresa", "[CUIT Empresa]", "organization.cuit"),
            _field("afiliacion.afiliado", "¿Está afiliado? (SI/NO)", "[Afiliado SI/NO]", required=True, options=["SI", "NO"]),
            _field("afiliacion.numero", "Número de Afiliado", "[N° de Afiliado (si corresponde)]", required=False),
            _field("afiliacion.sindicato", "Nombre del Sindicato", "[Nombre del Sindicato]", required=False),
        ],
    },
    "CTTD-004": {
        "code": "CTTD-004", "category": "ASOCIACIONES PROFESIONALES", "model_label": "Modelo N° 9",
        "title": "Contrato de Trabajo por Tiempo Determinado / Plazo Fijo (Art. 93 L.C.T.)",
        "description": "Contrato de trabajo a plazo fijo conforme al artículo 93 L.C.T.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Contrato Trabajo Plazo Fijo CTTD-004 MyManageRH.pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empresa.razon_social", "Razón Social", "[Razón Social de la Empresa]", "organization.name"),
            _field("empresa.cuit", "CUIT de la Empresa", "[CUIT Empresa]", "organization.cuit"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL/DNI]", "employee.cuil_or_dni"),
            _field("empleado.nacionalidad", "Nacionalidad", "[Nacionalidad]", "employee.nationality"),
            _field("empleado.edad", "Edad", "[Edad]", "employee.age"),
            _field("empleado.domicilio_completo", "Domicilio", "[Domicilio del Trabajador]", "employee.address"),
            _field("contrato.justificacion", "Tareas / Justificación de Modalidad", "[Descripción de Tareas / Justificación Modalidad]"),
            _field("contrato.fecha_fin", "Fecha de Fin del Contrato", "[Fecha Fin del Contrato]", input_type="date"),
            _field("empleo.horario", "Horario de Trabajo", "[Horario de Trabajo]"),
            _field("empleo.remuneracion", "Remuneración Inicial ($)", "[Remuneración Inicial ($)]"),
            _field("empleo.incremento", "Pauta / Criterio de Incremento", "[Pauta / Criterio de Incremento]"),
        ],
    },
    "CTE-005": {
        "code": "CTE-005", "category": "ASOCIACIONES PROFESIONALES", "model_label": "Modelo N° 10",
        "title": "Contrato de Trabajo Eventual (Arts. 68 a 74, Ley 24.013)",
        "description": "Contrato de trabajo eventual conforme a la Ley 24.013.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Contrato Trabajo Eventual CTE-005 MyManageRH.pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empresa.razon_social", "Razón Social", "[Razón Social de la Empresa]", "organization.name"),
            _field("empresa.cuit", "CUIT de la Empresa", "[CUIT Empresa]", "organization.cuit"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL/DNI]", "employee.cuil_or_dni"),
            _field("empleado.nacionalidad", "Nacionalidad", "[Nacionalidad]", "employee.nationality"),
            _field("empleado.edad", "Edad", "[Edad]", "employee.age"),
            _field("empleado.domicilio_completo", "Domicilio", "[Domicilio del Trabajador]", "employee.address"),
            _field("empleo.puesto", "Puesto / Cargo", "[Puesto / Cargo]", "employee.job_title"),
            _field("contrato.tareas_eventuales", "Tareas Extraordinarias y Transitorias", "[Detalle de Tareas Extraordinarias y Transitorias]"),
            _field("empleo.horario", "Horario de Trabajo", "[Horario de Trabajo]"),
        ],
    },
    "NEA-006": {
        "code": "NEA-006", "category": "ASOCIACIONES PROFESIONALES", "model_label": "Modelo N° 11",
        "title": "Nota del Empleador al Trabajador Notificando Inicio de Temporada (Art. 98 L.C.T.)",
        "description": "Notificación al trabajador del inicio de temporada según el artículo 98 L.C.T.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Notificacion Temporada NEA-006 MyManageRH.pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.fecha_emision", "Fecha de Emisión", "[Fecha de Emisión]", "system.today"),
            _field("empresa.razon_social", "Razón Social", "[Razón Social de la Empresa]", "organization.name"),
            _field("empresa.cuit", "CUIT de la Empresa", "[CUIT Empresa]", "organization.cuit"),
            _field("empleado.apellido_y_nombre", "Nombre y Apellido", "[Nombre y Apellido]", "employee.full_name"),
            _field("empleado.cuil", "CUIL / DNI", "[CUIL/DNI]", "employee.cuil_or_dni"),
            _field("empleado.domicilio_completo", "Domicilio", "[Domicilio del Trabajador]", "employee.address"),
            _field("temporada.dia_inicio", "Día de Inicio", "[Día de Inicio]", "system.day"),
            _field("temporada.mes_inicio", "Mes de Inicio", "[Mes de Inicio]", "system.month_name"),
            _field("temporada.anio_inicio", "Año de Inicio", "[Año de Inicio]", "system.year"),
            _field("empleo.horario", "Horario de Trabajo Habitual", "[Horario de Trabajo habitual]"),
        ],
    },
    "CTT-007": {
        "code": "CTT-007", "category": "ASOCIACIONES LABORALES", "model_label": "Modelo Estándar (Arts. 96-98 L.C.T.)",
        "title": "Contrato de Trabajo de Temporada",
        "description": "Contrato de trabajo de temporada conforme a los artículos 96 a 98 L.C.T.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Contrato Temporada CTT-007 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar_celebracion", "Lugar de Celebración", "[Lugar de Celebración]", "organization.city"),
            _field("documento.dia_celebracion", "Día de Celebración", "[Día de Celebración]", "system.day"),
            _field("documento.mes_celebracion", "Mes de Celebración", "[Mes de Celebración]", "system.month_name"),
            _field("documento.anio_celebracion", "Año de Celebración", "[Año de Celebración]", "system.year"),
            _field("empresa.razon_social", "Empleador", "[Nombre o Denominación del Empleador]", "organization.name"),
            _field("empresa.domicilio", "Domicilio del Empleador", "[Domicilio del Empleador]"),
            _field("empresa.ciudad", "Ciudad del Empleador", "[Ciudad del Empleador]", "organization.city"),
            _field("empresa.provincia", "Provincia del Empleador", "[Provincia del Empleador]", "organization.province"),
            _field("empresa.representante_legal", "Representante Legal", "[Representante Legal]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.cuil", "CUIL", "[CUIL del Trabajador]", "employee.cuil"),
            _field("empleado.domicilio_completo", "Domicilio del Trabajador", "[Domicilio del Trabajador]", "employee.address"),
            _field("empleado.ciudad", "Ciudad del Trabajador", "[Ciudad del Trabajador]", "employee.city"),
            _field("empleado.provincia", "Provincia del Trabajador", "[Provincia del Trabajador]", "employee.province"),
            _field("temporada.dia_inicio_ciclo", "Día de Inicio del Ciclo Anual", "[Día de Inicio del Ciclo Anual]"),
            _field("temporada.dia_fin_ciclo", "Día de Fin del Ciclo Anual", "[Día de Fin del Ciclo Anual]"),
            _field("empleo.tareas", "Descripción de Tareas", "[Descripción de Tareas]", "employee.task"),
            _field("temporada.fecha_inicio", "Fecha Inicio de Temporada", "[Fecha Inicio de Temporada]", input_type="date"),
            _field("temporada.fecha_fin", "Fecha Fin de Temporada", "[Fecha Fin de Temporada]", input_type="date"),
            _field("empleo.modalidad_liquidacion", "Modalidad de Liquidación", "[Modalidad de Liquidación]"),
            _field("empleo.remuneracion", "Monto del Sueldo ($)", "[Monto del Sueldo ($)]"),
            _field("empleo.remuneracion_letras", "Monto en Letras", "[Monto en Letras]"),
            _field("empleo.dias_jornada", "Días de Jornada Laboral", "[Días de Jornada Laboral]"),
            _field("empleo.horario", "Horario de Trabajo", "[Horario de Trabajo]"),
            _field("empleo.lugar_trabajo", "Lugar de Prestación de Tareas", "[Lugar de Prestación de Tareas]"),
        ],
    },
    "CTP-008": {
        "code": "CTP-008", "category": "ASOCIACIONES LABORALES", "model_label": "Modelo N° 11/1",
        "title": "Contrato de Trabajo a Tiempo Parcial (Ley 24.465, Art. 2° / Art. 92 ter L.C.T.)",
        "description": "Contrato de trabajo a tiempo parcial.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Contrato Tiempo Parcial CTP-008 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar", "Lugar", "[Lugar]", "organization.city"),
            _field("documento.dia_celebracion", "Día de Celebración", "[Día de Celebración]", "system.day"),
            _field("documento.mes_celebracion", "Mes de Celebración", "[Mes de Celebración]", "system.month_name"),
            _field("documento.anio_celebracion", "Año de Celebración", "[Año de Celebración]", "system.year"),
            _field("empresa.razon_social", "Empleadora", "[Nombre o Denominación de la Empleadora]", "organization.name"),
            _field("empresa.domicilio", "Domicilio de la Empleadora", "[Domicilio de la Empleadora]"),
            _field("empresa.representante_legal", "Representante Legal", "[Representante Legal]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.cuil", "CUIL", "[CUIL del Trabajador]", "employee.cuil"),
            _field("empleado.domicilio_completo", "Calle y Número", "[Calle y Número del Trabajador]", "employee.address"),
            _field("empleado.ciudad", "Ciudad", "[Ciudad del Trabajador]", "employee.city"),
            _field("empleado.nacionalidad", "Nacionalidad", "[Nacionalidad]", "employee.nationality"),
            _field("empleado.estado_civil", "Estado Civil", "[Estado Civil]", "employee.marital_status"),
            _field("empleo.tareas", "Descripción de Trabajos", "[Descripción de Trabajos]", "employee.task"),
            _field("documento.fecha_inicio", "Fecha de Inicio del Contrato", "[Fecha de Inicio del Contrato]", input_type="date"),
            _field("empleo.horario", "Horario de Trabajo", "[Horario de Trabajo]"),
            _field("empleo.lugar_trabajo", "Establecimiento / Lugar de Trabajo", "[Domicilio del Establecimiento / Lugar de Trabajo]"),
            _field("empleo.puesto", "Puesto / Función", "[Puesto / Función del Trabajador]", "employee.job_title"),
            _field("empleo.convenio", "Convenio Colectivo", "[Número de Convenio Colectivo]", "employee.union_agreement"),
            _field("empleo.categoria", "Categoría Profesional", "[Categoría Profesional]", "employee.category"),
            _field("empleo.remuneracion", "Remuneración ($)", "[Monto de Remuneración en Pesos]"),
        ],
    },
    "PPCT-009": {
        "code": "PPCT-009", "category": "ASOCIACIONES LABORALES", "model_label": "Modelo N° 11/2",
        "title": "Período de Prueba (Art. 92 bis L.C.T.) — Comunicación de Rescisión Laboral",
        "description": "Comunicación de rescisión durante el período de prueba.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Rescisión Período de Prueba PPCT-009 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar", "Lugar", "[Lugar]", "organization.city"),
            _field("documento.dia_emision", "Día de Emisión", "[Día de Emisión]", "system.day"),
            _field("documento.mes_emision", "Mes de Emisión", "[Mes de Emisión]", "system.month_name"),
            _field("documento.anio_emision", "Año de Emisión", "[Año de Emisión]", "system.year"),
            _field("empresa.razon_social", "Empleador", "[Nombre o Razó Social del Empleador]", "organization.name"),
            _field("empresa.domicilio", "Domicilio del Empleador", "[Domicilio del Empleador]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.cuil", "CUIL", "[CUIL del Trabajador]", "employee.cuil"),
            _field("contrato.fecha_rescision", "Fecha Efectiva de Rescisión", "[Fecha de Efectividad de Rescisión]", input_type="date"),
        ],
    },
    "CTI-010": {
        "code": "CTI-010", "category": "ASOCIACIONES LABORALES", "model_label": "Modelo Estándar (Ley 25.877)",
        "title": "Contrato de Trabajo por Tiempo Indeterminado con Período de Prueba Inicial (Art. 92 bis L.C.T.)",
        "description": "Contrato por tiempo indeterminado con período de prueba inicial.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Contrato Indeterminado CTI-010 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar", "Lugar de Celebración", "[Lugar de celebración del contrato]", "organization.city"),
            _field("documento.dia_celebracion", "Día de Celebración", "[Día de Celebración]", "system.day"),
            _field("documento.mes_celebracion", "Mes de Celebración", "[Mes de Celebración]", "system.month_name"),
            _field("documento.anio_celebracion", "Año de Celebración", "[Año de Celebración]", "system.year"),
            _field("empresa.razon_social", "Empleador", "[Nombre o denominación del empleador]", "organization.name"),
            _field("empresa.domicilio", "Domicilio del Empleador", "[Domicilio del Empleador]"),
            _field("empresa.ciudad", "Ciudad del Empleador", "[Ciudad del Empleador]", "organization.city"),
            _field("empresa.provincia", "Provincia del Empleador", "[Provincia del Empleador]", "organization.province"),
            _field("empresa.representante_legal", "Representante Legal", "[Representante Legal]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y apellido del trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.cuil", "CUIL", "[CUIL del Trabajador]", "employee.cuil"),
            _field("empleado.domicilio_completo", "Domicilio del Trabajador", "[Domicilio del Trabajador]", "employee.address"),
            _field("empleado.ciudad", "Ciudad del Trabajador", "[Ciudad del Trabajador]", "employee.city"),
            _field("empleado.provincia", "Provincia del Trabajador", "[Provincia del Trabajador]", "employee.province"),
            _field("documento.fecha_inicio", "Inicio de la Relación Laboral", "[Día de inicio de la relación laboral]", input_type="date"),
            _field("empleo.tareas", "Descripción de Tareas", "[Descripción de Tareas]", "employee.task"),
            _field("empleo.categoria", "Categoría Laboral", "[Categoría Laboral]", "employee.category"),
            _field("empleo.modalidad_liquidacion", "Modalidad de Liquidación", "[Modalidad de Liquidación]"),
            _field("empleo.remuneracion", "Monto del Sueldo ($)", "[Monto del Sueldo ($)]"),
            _field("empleo.remuneracion_letras", "Monto en Letras", "[Monto en Letras]"),
            _field("empleo.dias_jornada", "Días de Jornada Laboral", "[Días de Jornada Laboral]"),
            _field("empleo.horario", "Horario de Trabajo", "[Horario de Trabajo]"),
            _field("empleo.lugar_trabajo", "Lugar de Trabajo", "[Lugar de Trabajo]"),
            _field("empleo.convenio", "Convenio Colectivo (CCT)", "[CCT Nº]", "employee.union_agreement"),
        ],
    },
    "AAS-011": {
        "code": "AAS-011", "category": "DISCIPLINARIAS", "model_label": "Modelo N° 133",
        "title": "Amonestación Previa a la Aplicación de Sanciones Disciplinarias (Llegada Tarde)",
        "description": "Amonestación previa por llegada tarde.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Amonestacion Previa AAS-011 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar", "Lugar", "[Lugar]", "organization.city"),
            _field("documento.dia_emision", "Día de Emisión", "[Día de Emisión]", "system.day"),
            _field("documento.mes_emision", "Mes de Emisión", "[Mes de Emisión]", "system.month_name"),
            _field("documento.anio_emision", "Año de Emisión", "[Año de Emisión]", "system.year"),
            _field("empresa.razon_social", "Empleador", "[Nombre o Razón Social del Empleador]", "organization.name"),
            _field("empresa.domicilio", "Domicilio del Empleador", "[Domicilio del Empleador]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.file_number", "Número de Legajo", "[Número de Legajo]", "employee.file_number"),
            _field("infraccion.fecha", "Fecha de la Infracción", "[Fecha de la Infracción]", input_type="date"),
        ],
    },
    "AI-012": {
        "code": "AI-012", "category": "DISCIPLINARIAS", "model_label": "Modelo N° 134",
        "title": "Sanción Disciplinaria / Suspensión por Ausencia Injustificada",
        "description": "Sanción disciplinaria o suspensión por ausencia injustificada.", "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Sanción Ausencia Injustificada AI-012 MyManageRH.pdf",
        "fields": [
            _field("contrato.lugar", "Lugar", "[Lugar]", "organization.city"),
            _field("documento.dia_emision", "Día de Emisión", "[Día de Emisión]", "system.day"),
            _field("documento.mes_emision", "Mes de Emisión", "[Mes de Emisión]", "system.month_name"),
            _field("documento.anio_emision", "Año de Emisión", "[Año de Emisión]", "system.year"),
            _field("empresa.razon_social", "Empleador", "[Nombre o Razón Social del Empleador]", "organization.name"),
            _field("empresa.domicilio", "Domicilio del Empleador", "[Domicilio del Empleador]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni", "DNI", "[DNI del Trabajador]", "employee.dni"),
            _field("empleado.file_number", "Número de Legajo", "[Número de Legajo]", "employee.file_number"),
            _field("ausencia.dia", "Día de Ausencia", "[Día de Ausencia]", input_type="date"),
            _field("suspension.fecha_inicio", "Inicio de Suspensión", "[Fecha Inicio Suspensión]", input_type="date"),
            _field("suspension.fecha_fin", "Fin de Suspensión", "[Fecha Fin Suspensión]", input_type="date"),
        ],
    },
    "ERT-013": {
        "code": "ERT-013", "category": "Construccion", "model_label": "Constancia de entrega",
        "title": "Constancia de Entrega de Ropa de Trabajo para la Industria de la Construcción",
        "description": "Constancia de entrega de ropa de trabajo y elementos de protección personal conforme al CCT 76/75.",
        "version": "1.0",
        "template_path": "Modelos Laborales/Plantilla Entrega Ropa Trabajo ERT-013 MyManageRH.pdf",
        "fields": [
            _field("empresa.localidad_emision", "Lugar de Emisión", "[Lugar de Emisión]", "organization.city"),
            _field("documento.dia_emision", "Día de Emisión", "[Día]", "system.day"),
            _field("documento.mes_emision", "Mes de Emisión", "[Mes]", "system.month_name"),
            _field("documento.anio_emision", "Año de Emisión", "[Año]", "system.year"),
            _field("empresa.razon_social", "Razón Social", "[Empresa]", "organization.name"),
            _field("obra.denominacion", "Obra", "[Nombre / Denominación de la Obra]"),
            _field("empleado.apellido_y_nombre", "Trabajador", "[Nombre y Apellido del Trabajador]", "employee.full_name"),
            _field("empleado.dni_cuil", "DNI / CUIL", "[Número de DNI / CUIL]", "employee.cuil_or_dni"),
            _field("ropa.fecha_inicio_periodo", "Inicio del Período", "[Fecha Inicio Período]", input_type="date"),
            _field("ropa.fecha_fin_periodo", "Fin del Período", "[Fecha Fin Período]", input_type="date"),
            _field("ropa.fecha_vencimiento_entrega", "Vencimiento de la Entrega", "[Fecha Vencimiento Entrega]", input_type="date"),
            _field("ropa.fecha_proximo_vencimiento", "Próximo Vencimiento", "[Fecha Próximo Vencimiento]", input_type="date"),
            _field("firma.trabajador", "Firma del Trabajador (opcional)", "[Firma del Trabajador]", required=False),
            _field("firma.aclaracion", "Aclaración (opcional)", "[Aclaración]", required=False),
            _field("firma.aclaracion_nombre", "Aclaración de Firma (opcional)", "[ACLARACIÓN DE FIRMA]", required=False),
            _field("firma.empleador", "Firma / Sello de la Empresa (opcional)", "[Firma / Sello Empresa]", required=False),
        ],
    },
}


def catalog() -> list[dict[str, Any]]:
    return [
        {**model, "template_filename": Path(model["template_path"]).name}
        for model in MODEL_CATALOG.values()
    ]


def get_model(code: str) -> dict[str, Any]:
    try:
        return MODEL_CATALOG[code]
    except KeyError as exc:
        raise ValueError("labor_model_not_found") from exc


def _address(row: Any) -> str:
    street = " ".join(part for part in (row["address"], row["address_number"]) if part)
    locality = ", ".join(part for part in (row["city"], row["province"]) if part)
    postal = f"CP {row['postal_code']}" if row["postal_code"] else ""
    return ", ".join(part for part in (street, locality, postal) if part)


def resolve_fields(db: Session, organization_id: str, employee_id: Optional[str] = None, template_code: str = "TLG-INT-001") -> dict[str, Any]:
    organization = db.execute(text("""
        SELECT id, name, cuit, city, province, zip_code
        FROM organizations WHERE id = :org
    """), {"org": organization_id}).mappings().first()
    if not organization:
        raise ValueError("organization_not_found")

    employee = None
    if employee_id:
        employee = db.execute(text("""
            SELECT id, first_name, last_name, dni, cuil, address, address_number,
                   city, province, postal_code, nationality, birth_date,
                   marital_status, file_number, job_title, category, task,
                   union_agreement
            FROM employees
            WHERE id = :employee AND organization_id = :org
              AND is_deleted = false AND is_active = true
        """), {"employee": employee_id, "org": organization_id}).mappings().first()
        if not employee:
            raise ValueError("employee_not_found")

    now = datetime.now()
    month_names = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    full_name = " ".join(part for part in (employee["first_name"], employee["last_name"]) if part) if employee else ""
    age = ""
    if employee and employee["birth_date"]:
        birth_date = employee["birth_date"]
        age = str(now.year - birth_date.year - ((now.month, now.day) < (birth_date.month, birth_date.day)))

    source_values = {
        "organization.name": organization["name"] or "",
        "organization.cuit": organization["cuit"] or "",
        "organization.city": organization["city"] or "",
        "organization.province": organization["province"] or "",
        "system.today": now.strftime("%Y-%m-%d"),
        "system.day": now.strftime("%d"),
        "system.month_name": month_names[now.month - 1],
        "system.year": now.strftime("%Y"),
        "employee.full_name": full_name,
        "employee.dni": employee["dni"] or "" if employee else "",
        "employee.cuil": employee["cuil"] or "" if employee else "",
        "employee.cuil_or_dni": (employee["cuil"] or employee["dni"] or "") if employee else "",
        "employee.address": _address(employee) if employee else "",
        "employee.city": employee["city"] or "" if employee else "",
        "employee.province": employee["province"] or "" if employee else "",
        "employee.nationality": employee["nationality"] or "" if employee else "",
        "employee.age": age,
        "employee.file_number": employee["file_number"] or "" if employee else "",
        "employee.job_title": employee["job_title"] or "" if employee else "",
        "employee.category": employee["category"] or "" if employee else "",
        "employee.task": employee["task"] or "" if employee else "",
        "employee.union_agreement": employee["union_agreement"] or "" if employee else "",
        "employee.marital_status": employee["marital_status"] or "" if employee else "",
    }
    fields = {}
    for field in get_model(template_code)["fields"]:
        source_value = source_values.get(field.get("source", ""), "")
        fields[field["key"]] = source_value if source_value not in (None, "") else field.get("default", "")
    return fields


def pending_fields(fields: dict[str, Any], code: str) -> list[str]:
    model = get_model(code)
    return [field["key"] for field in model["fields"] if field["required"] and not str(fields.get(field["key"], "")).strip()]


def _normalize_display_date(value: str) -> str:
    if not value:
        return ""
    candidate = str(value).strip()
    if not candidate:
        return ""
    try:
        if len(candidate) == 10 and candidate[4] == '-' and candidate[7] == '-':
            dt = datetime.strptime(candidate, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
    except ValueError:
        pass
    if "/" in candidate:
        return candidate
    try:
        dt = datetime.strptime(candidate, "%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        pass
    return candidate


def _fit_font(value: str, rect: fitz.Rect, max_size: float = 11.8) -> float:
    size = max_size
    while size > 7 and fitz.get_text_length(value, fontname="helv", fontsize=size) > rect.width:
        size -= 0.25
    return size


def _replace(page: fitz.Page, placeholder: str, value: str, prefer_last: bool = False) -> int:
    boxes = page.search_for(placeholder)
    if not boxes or not value:
        return 0
    if prefer_last:
        last_box = sorted(boxes, key=lambda box: (box.y0, box.x0))[-1]
        for box in boxes:
            page.add_redact_annot(box, fill=(1, 1, 1))
        page.apply_redactions()
        page.insert_text(fitz.Point(last_box.x0, last_box.y1 - 1.2), value, fontname="helv", fontsize=_fit_font(value, last_box), color=(0.06, 0.09, 0.16), overlay=True)
        return len(boxes)
    for box in boxes:
        page.add_redact_annot(box, fill=(1, 1, 1))
    page.apply_redactions()
    for box in boxes:
        page.insert_text(fitz.Point(box.x0, box.y1 - 1.2), value, fontname="helv", fontsize=_fit_font(value, box), color=(0.06, 0.09, 0.16), overlay=True)
    return len(boxes)


def _replace_variants(page: fitz.Page, value: str, candidates: list[str], prefer_last: bool = False) -> int:
    if not value:
        return 0
    for candidate in candidates:
        replaced = _replace(page, candidate, value, prefer_last=prefer_last)
        if replaced:
            return replaced
    return 0


def render_instance(db: Session, document_id: str, organization_id: str) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT id, template_code, template_path, fields, employee_id, status
        FROM labor_model_documents
        WHERE id = :id AND organization_id = :org
    """), {"id": document_id, "org": organization_id}).mappings().first()
    if not row:
        raise ValueError("labor_document_not_found")
    if row["status"] in ("FIRMADO", "ENVIADO"):
        raise ValueError("labor_document_locked")

    template = Path(row["template_path"])
    if not template.is_absolute():
        template = ROOT / template
    if not template.is_file() and not Path(row["template_path"]).is_absolute():
        relocated_template = (ROOT / "Modelos Laborales" / Path(row["template_path"]).name).resolve()
        try:
            relocated_template.relative_to(ROOT.resolve())
            if relocated_template.is_file():
                template = relocated_template
        except ValueError:
            pass
    if not template.exists():
        raise FileNotFoundError("labor_model_template_missing")

    fields = row["fields"] or {}
    output_rel = f"labor_models/{organization_id}/{document_id}/rendered.pdf"
    output = Path(ALLOWED_STORAGE_DIR) / output_rel
    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(str(template))
    page = document[0]
    occurrences = {}
    for field in get_model(row["template_code"])["fields"]:
        value = str(fields.get(field["key"], "") or "").strip()
        if value and field.get("input_type") == "date":
            value = _normalize_display_date(value)
        marker = field["marker"]
        if value:
            occurrences[field["key"]] = _replace(page, marker, value)
        else:
            boxes = page.search_for(marker)
            occurrences[field["key"]] = 0
            if boxes and not field.get("required", True):
                for box in boxes:
                    page.add_redact_annot(box, fill=(1, 1, 1))
                page.apply_redactions()
    document.set_metadata({"title": f"{row['template_code']} - MyManageRH", "subject": "Modelo Laboral"})
    document.save(str(output), garbage=4, deflate=True)
    document.close()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    db.execute(text("""
        UPDATE labor_model_documents
        SET rendered_pdf_path = :path, rendered_pdf_sha256 = :hash,
            updated_at = :now,
            status = CASE WHEN status = 'BORRADOR' THEN 'LISTO_PARA_FIRMAR' ELSE status END
        WHERE id = :id AND organization_id = :org
    """), {"path": output_rel, "hash": digest, "now": utc_now(), "id": document_id, "org": organization_id})
    db.commit()
    return {"path": str(output), "sha256": digest, "occurrences": occurrences}


ROOT = Path(__file__).resolve().parents[1]