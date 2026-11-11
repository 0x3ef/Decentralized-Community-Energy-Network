const messages: Record<string, string> = {
  "Community requires verified governance activation":
    "La comunidad requiere una activación de gobernanza confirmada.",
  "Native settlement deployment is not registered":
    "La comunidad todavía no tiene contratos de liquidación nativa registrados.",
  "Verified wallet required":
    "Verifica la propiedad de tu wallet antes de continuar.",
  "No verified wallet linked":
    "Vincula y verifica una wallet para consultar el protocolo.",
  "Contract rejected the requested operation":
    "El contrato rechazó la operación. Revisa el saldo, la autorización SUN y el estado del protocolo.",
  "Registrar or configured timelock proposer required":
    "Se requiere un rol de registro o de proponente del timelock configurado.",
  "Confirmed community registry required":
    "Se requiere un registro de comunidad confirmado en cadena.",
  "Invalid credentials": "El correo o la contraseña no son correctos.",
  "Home not found": "El hogar no está disponible para tu cuenta.",
  "Devices not found for the home":
    "Este hogar todavía no tiene dispositivos registrados.",
  "Device not found": "El dispositivo no está disponible para tu cuenta.",
};
export function localizedApiError(status: number, detail?: string) {
  return (
    (detail && messages[detail]) ||
    ({
      400: "El servidor rechazó la operación. Revisa los datos y el estado del protocolo.",
      401: "El correo, la contraseña o la sesión no son válidos.",
      403: "No tienes autorización para esta operación.",
      404: "El recurso no está disponible.",
      409: "La operación entra en conflicto con el estado actual.",
      422: "Revisa los datos introducidos.",
    }[status] ??
      `El servidor respondió ${status}. Inténtalo de nuevo.`)
  );
}
