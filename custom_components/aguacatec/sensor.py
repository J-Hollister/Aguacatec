import logging
import asyncio
import csv
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from datetime import timedelta

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

CACHE_DURATION = timedelta(minutes=10)

CAMPOS_SENSORES = {
    "Categoría":             {"nombre": "Categoría",           "icono": "mdi:egg-outline"},
    "Suscripción":           {"nombre": "Suscripción",         "icono": "mdi:calendar-sync"},
    "Aguacoins":             {"nombre": "Aguacoins",           "icono": "mdi:checkbox-multiple-blank-circle"},
    "HA Companion":          {"nombre": "HA Companion",        "icono": "mdi:watch"},  
    "Sesiones Extra":        {"nombre": "Sesiones Extra",      "icono": "mdi:lifebuoy"},
    "Tarjetas":              {"nombre": "Tarjetas",            "icono": "mdi:palette"},
    "Premio":                {"nombre": "Sorteo Premiado",     "icono": "mdi:trophy-award"},
    "Numeros Sorteo":        {"nombre": "Números Sorteo",      "icono": "mdi:ticket"},
    "Fecha último sorteo":   {"nombre": "Fecha Último Sorteo", "icono": "mdi:calendar-star"},
    "Fecha próximo sorteo":  {"nombre": "Fecha Próximo Sorteo","icono": "mdi:calendar"},
    "Nº premiado":           {"nombre": "Número Premiado",     "icono": "mdi:trophy"},
    "Ganador":               {"nombre": "Ultimo Ganador",      "icono": "mdi:party-popper"},
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    config = hass.data[DOMAIN][entry.entry_id]
    session = async_get_clientsession(hass)

    coordinator = AguacatecCoordinator(hass, config, session)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"config": config, "coordinator": coordinator}

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{config['id_aguacatec']}_{config['user_telegram']}")},
        name=f"Aguacatec {config['user_telegram']}",
        manufacturer="Aguacatec",
        model="Información de Aguacatec",
        sw_version=VERSION,
    )

    sensores = []
    datos = coordinator.data or {}

    for clave, info in CAMPOS_SENSORES.items():
        if clave in datos:
            sensores.append(
                AguacatecSensor(coordinator, clave, config["user_telegram"], info["icono"], device_info)
            )

    if not sensores:
        sensores.append(
            AguacatecSensor(coordinator, "estado", config["user_telegram"], "mdi:alert", device_info)
        )

    async_add_entities(sensores)


class AguacatecCoordinator(DataUpdateCoordinator):
    """Coordinator central que gestiona las actualizaciones de datos."""

    def __init__(self, hass: HomeAssistant, config: dict, session):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=CACHE_DURATION,
        )
        self._usuario = config["user_telegram"]
        self._id_spreadsheet = config["id_aguacatec"]
        self._session = session
        self._max_retries = 5
        self._base_delay = 3

    async def _async_update_data(self):
        """Método que llama HA automáticamente cada `update_interval`."""
        try:
            return await self._obtener_datos()
        except Exception as e:
            raise UpdateFailed(f"Error al obtener datos de Aguacatec: {e}") from e

    async def _fetch_with_retry(self, url: str) -> str | None:
        """Solicitud HTTP con reintentos y backoff exponencial."""
        for intento in range(self._max_retries):
            try:
                async with asyncio.timeout(15):
                    async with self._session.get(url) as respuesta:
                        if respuesta.status == 200:
                            return await respuesta.text()
                        elif respuesta.status == 429:
                            delay = self._base_delay * (2 ** intento)
                            _LOGGER.warning("Error 429 en %s. Reintentando en %ss...", url, delay)
                            await asyncio.sleep(delay)
                        else:
                            _LOGGER.error("Error %s al obtener %s", respuesta.status, url)
                            return None
            except Exception as e:
                _LOGGER.error("Excepción al obtener %s: %s", url, e)
                return None
        return None

    async def _obtener_datos(self) -> dict:
        resultado = {}
        base_url = f"https://docs.google.com/spreadsheets/d/{self._id_spreadsheet}/export?format=csv&id={self._id_spreadsheet}"

        # Hoja principal (Aguacoins, Categoría, etc.)
        texto = await self._fetch_with_retry(f"{base_url}&gid=0")
        if texto:
            reader = csv.reader(texto.splitlines())
            cabeceras = next(reader, None)
            if cabeceras:
                for row in reader:
                    if row and row[0] == self._usuario:
                        resultado.update(dict(zip(cabeceras[1:], row[1:])))
                        break

        # Números de sorteo
        texto = await self._fetch_with_retry(f"{base_url}&gid=809535125")
        if texto:
            numeros = []
            reader = csv.reader(texto.splitlines())
            next(reader, None)
            for row in reader:
                if len(row) >= 2 and self._usuario in row[1]:
                    numeros.append(row[0])
            if numeros:
                resultado["Numeros Sorteo"] = numeros

        # Datos del sorteo
        texto = await self._fetch_with_retry(f"{base_url}&gid=992544740")
        if texto:
            reader = csv.reader(texto.splitlines())
            next(reader, None)
            for row in reader:
                if len(row) >= 2 and row[0].strip() in CAMPOS_SENSORES:
                    resultado[row[0].strip()] = row[1].strip() or "Vacío"

        if not resultado:
            raise UpdateFailed("No se obtuvieron datos del servidor.")

        return resultado


class AguacatecSensor(SensorEntity):
    """Sensor individual para cada parámetro de Aguacatec."""

    def __init__(self, coordinator: AguacatecCoordinator, clave: str, usuario: str, icono: str, device_info: DeviceInfo):
        self._coordinator = coordinator
        self._clave = clave
        self._usuario = usuario
        self._attr_icon = icono
        self._attr_device_info = device_info
        nombre = CAMPOS_SENSORES.get(clave, {"nombre": clave})["nombre"]
        self._attr_name = nombre
        # Usuario incluido para evitar colisiones entre distintos usuarios
        self._attr_unique_id = f"{DOMAIN}_{usuario}_{clave.lower().replace(' ', '_')}"

    @property
    def state(self):
        datos = self._coordinator.data or {}
        valor = datos.get(self._clave)
        if valor is None:
            return "Sin datos" if self._clave != "estado" else "Usuario no encontrado"
        return ", ".join(valor) if isinstance(valor, list) else valor

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    async def async_update(self):
        await self._coordinator.async_request_refresh()
