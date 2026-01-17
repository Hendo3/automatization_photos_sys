import json
import logging

from jsonschema import ValidationError, validate

import config  # Importa o config robusto

# Configura o logger (vai herdar o nível DEBUG se -v for passado)
logger = config.setup_logging(__name__)

# --- SCHEMAS (Mantidos inalterados e completos) ---
TEMPLATE_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^.*$": { 
            "type": "object",
            "required": ["pos_x", "pos_y", "max_width_pixels", "font_size", "color"],
            "additionalProperties": False,
            "properties": {
                "comment": {"type": "string"},
                "pos_x": {"type": "integer"},
                "pos_y": {"type": "integer"},
                "max_width_pixels": {"type": "integer", "minimum": 1},
                "font_name": {"type": ["string", "null"]},
                "font_size": {"type": "integer", "minimum": 1},
                "color": {
                    "type": "string",
                    "pattern": "^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$"
                },
                "align": {"type": "string", "enum": ["left", "center", "right"]}
            }
        }
    }
}

PEDIDOS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["output_pdf", "input_pdf_base", "pagina_frente"],
        "properties": {
            "output_pdf": {"type": "string", "minLength": 1},
            "input_pdf_base": {"type": "string", "minLength": 1},
            "pagina_frente": {
                "type": "object",
                "required": ["template_imagem", "texto"],
                "properties": {
                    "template_imagem": {"type": "string", "minLength": 1},
                    "texto": {"type": "string"},
                    "fonte": {"type": ["string", "null"]}
                }
            }
        }
    }
}

# --- FUNÇÃO DE VALIDAÇÃO COM VERBOSE ---

def validate_data(data, schema_type: str) -> bool:
    """
    Valida dados. Se config.IS_VERBOSE for True, loga o sucesso.
    """
    schema = None
    if schema_type == 'templates':
        schema = TEMPLATE_SCHEMA
    elif schema_type == 'pedidos':
        schema = PEDIDOS_SCHEMA
    else:
        logger.error(f"Erro interno: Tipo de schema desconhecido '{schema_type}'")
        return False

    try:
        if config.IS_VERBOSE:
            logger.debug(f"Iniciando validação do schema: {schema_type.upper()}...")
            # Opcional: Logar o tamanho dos dados para debug
            if isinstance(data, list):
                logger.debug(f"Validando lista com {len(data)} itens.")
            elif isinstance(data, dict):
                logger.debug(f"Validando dicionário com {len(data)} chaves.")

        validate(instance=data, schema=schema)
        
        # AQUI ESTÁ O QUE VOCÊ PEDIU: Feedback visual no modo verbose
        if config.IS_VERBOSE:
            logger.info(f"✔ Sucesso: Schema '{schema_type}' validado perfeitamente.")
            
        return True

    except ValidationError as e:
        path = " -> ".join([str(p) for p in e.path]) if e.path else "Raiz"
        # Usamos logger.error sempre, independente do verbose, pois é erro
        logger.error(f"❌ FALHA DE VALIDAÇÃO [{schema_type.upper()}]")
        logger.error(f"   Local: {path}")
        logger.error(f"   Motivo: {e.message}")
        
        # Se estiver em verbose, dumpa o pedaço dos dados que falhou (útil para debug)
        if config.IS_VERBOSE:
            logger.debug(f"   Dados inválidos (instância): {e.instance}")
            
        return False

    except Exception as e:
        logger.critical(f"Erro inesperado na validação de '{schema_type}': {e}")
        return False