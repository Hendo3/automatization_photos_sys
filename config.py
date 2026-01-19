import logging
import os
import sys
from pathlib import Path


# --- DETECÇÃO DE RAIZ (MODO PARANOICO) ---
def find_app_root():
    print("\n--- INICIANDO DIAGNÓSTICO DE CAMINHO ---")
    
    candidates = []
    
    # 1. Sys.Executable (Onde o binário diz que está)
    if getattr(sys, 'frozen', False):
        p = Path(sys.executable).resolve().parent
        candidates.append(("sys.executable", p))
    
    # 2. Sys.Argv[0] (O comando que chamou o binário)
    if sys.argv and sys.argv[0]:
        p = Path(sys.argv[0]).resolve().parent
        candidates.append(("sys.argv[0]", p))
        
    # 3. CWD (Onde você está pisando agora no terminal)
    p = Path.cwd()
    candidates.append(("os.getcwd()", p))
    
    # 4. __file__ (Só pra garantir se não for frozen)
    if not getattr(sys, 'frozen', False):
        p = Path(__file__).resolve().parent
        candidates.append(("__file__", p))

    # --- TESTE DA PASTA FONTS ---
    # Nova estrutura: a âncora é 'input/fonts'. Só aceitamos o caminho se ela existir lá.
    
    final_path = None
    
    for method, path in candidates:
        fonts_path = path / "input" / "fonts"
        exists = fonts_path.exists()
        print(f"[{method}] Testando: {path}")
        print(f"   -> Pasta 'input/fonts' existe aqui? {'SIM! ✅' if exists else 'NÃO ❌'}")
        
        if exists and final_path is None:
            final_path = path
            
    print("----------------------------------------")
    
    if final_path:
        print(f"WINNER: Usando caminho -> {final_path}\n")
        return final_path
    else:
        # Se fodeu tudo, usa o CWD e reza
        print("CRITICAL: Nenhum caminho válido achado. Usando CWD como fallback.")
        return Path.cwd()

APP_ROOT = find_app_root()

# --- DIRETÓRIOS (nova estrutura) ---
DIR_INPUT = APP_ROOT / "input"
DIR_FONTS = DIR_INPUT / "fonts"
DIR_PDF = DIR_INPUT / "pdf"
DIR_PICTURES = DIR_INPUT / "pictures"

DIR_OUTPUT = APP_ROOT / "output"
DIR_TEMP = APP_ROOT / "temp_pdf_extract"

# --- ARQUIVOS ---
FILE_TEMPLATES_CONFIG = APP_ROOT / "templates.json"
FILE_PEDIDOS_DATA = APP_ROOT / "pedidos_pdf_duas_paginas.json"
FILE_TEMPLATE_MAP = APP_ROOT / "template_map.json"
FILE_LOG = APP_ROOT / "app_debug.log"

# --- CONSTANTES ---
UI_THEME_MODE = "Dark"
UI_COLOR_THEME = "blue"
# DEFAULT_FONT: chave padrão dentro do templates.json
# FALLBACK_FONT: arquivo usado quando a fonte do template/override falhar
DEFAULT_FONT = "font_name"
FALLBACK_FONT = "FreeMono.otf"

# Compatibilidade: código legado usa DEFAULT_FONT_NAME
DEFAULT_FONT_NAME = FALLBACK_FONT
IS_VERBOSE = True

# --- LOGGING ---
def setup_logging(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        try:
            fh = logging.FileHandler(FILE_LOG, encoding='utf-8')
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except: pass
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

# --- UTILITÁRIOS ---
def ensure_directories():
    try:
        DIR_INPUT.mkdir(parents=True, exist_ok=True)
        DIR_FONTS.mkdir(parents=True, exist_ok=True)
        DIR_PDF.mkdir(parents=True, exist_ok=True)
        DIR_PICTURES.mkdir(parents=True, exist_ok=True)
        DIR_OUTPUT.mkdir(parents=True, exist_ok=True)
    except:
        pass