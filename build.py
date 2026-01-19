import os
import shutil
from pathlib import Path

import customtkinter
import PyInstaller.__main__

# --- CONFIGURAÇÕES ---
WORK_DIR = Path(__file__).parent
DIST_DIR = WORK_DIR / "dist"
BUILD_DIR = WORK_DIR / "build"
FINAL_DIR = DIST_DIR / "ENTREGA_FINAL"

# Define o separador de caminhos (Windows usa ; Linux usa :)
SEP = ';' if os.name == 'nt' else ':'

def clean_previous_builds():
    print("--- Limpando builds anteriores ---")
    if DIST_DIR.exists(): shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists(): shutil.rmtree(BUILD_DIR)
    print("✓ Limpeza concluída.")

def get_customtkinter_path():
    """Localiza a pasta da biblioteca para incluir no build"""
    return os.path.dirname(customtkinter.__file__)

def build_exe(script_name, exe_name, icon_name="app_icon.ico"):
    print(f"\n--- Compilando {exe_name} ---")
    
    ctk_path = get_customtkinter_path()
    
    # Argumentos do PyInstaller
    args = [
        script_name,
        f'--name={exe_name}',
        '--onefile',       # Gera um único arquivo .exe
        '--noconsole',     # Não mostra a tela preta do terminal
        '--clean',
        f'--icon={icon_name}',
        
        # INCLUSÃO DE DADOS (SOURCE;DEST)
        # CustomTkinter (Obrigatório para não crashar)
        f'--add-data={ctk_path}{SEP}customtkinter',
        
        # Validadores e Configs (Embutidos no código, mas garantindo assets se usar MEIPASS)
        f'--add-data=templates.json{SEP}.',
    ]

    # Imports ocultos que as vezes o PyInstaller não acha
    hidden_imports = [
        '--hidden-import=PIL',
        '--hidden-import=PIL._tkinter_finder',
        '--hidden-import=fitz',
        '--hidden-import=customtkinter',
        '--hidden-import=jsonschema',
    ]
    
    PyInstaller.__main__.run(args + hidden_imports)
    print(f"✓ {exe_name} compilado com sucesso.")

def organize_output():
    """
    O PyInstaller --onefile cria o EXE, mas seu config.py espera encontrar
    a pasta 'input' (com 'fonts', 'pictures', 'pdf') AO LADO do executável
    para serem editáveis.
    Esta função prepara a pasta final para você zipar e mandar pro cliente.
    """
    print("\n--- Organizando Pasta de Entrega ---")
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Move os EXEs gerados
    for exe in DIST_DIR.glob("*.exe"):
        shutil.move(str(exe), str(FINAL_DIR / exe.name))
        print(f"-> Movido: {exe.name}")
    
    # Se estiver no Linux rodando Wine/Cross ou teste, pode gerar binário sem extensão
    if os.name != 'nt':
        for exe in DIST_DIR.glob("*"):
            if exe.is_file() and not exe.name.startswith(".") and "ENTREGA" not in str(exe):
                try:
                    shutil.move(str(exe), str(FINAL_DIR / exe.name))
                except: pass

    # 2. Copia Pastas Essenciais (Nova estrutura: input/*)
    # Isso é necessário porque seu config.py usa APP_ROOT (externo) para facilitar edição
    dirs_to_copy = ["input"]
    files_to_copy = [
        "templates.json",
        "pedidos_pdf_duas_paginas.json",
        "template_map.json",
        "LICENSE",
    ]

    for d in dirs_to_copy:
        src = WORK_DIR / d
        dst = FINAL_DIR / d
        if src.exists():
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"-> Copiado diretório: {d}/")
        else:
            print(f"AVISO: Diretório {d} não encontrado na raiz.")

    for f in files_to_copy:
        src = WORK_DIR / f
        dst = FINAL_DIR / f
        if src.exists():
            shutil.copy2(src, dst)
            print(f"-> Copiado arquivo: {f}")

    print(f"\n✅ SUCCESSO! Tudo pronto em: {FINAL_DIR}")
    print("Basta zipar essa pasta e mandar para o cliente.")

if __name__ == "__main__":
    # Garante que temos o ícone antes de começar
    if not Path("app_icon.ico").exists():
        print("Gerando ícone temporário...")
        try:
            import gerar_icone
            gerar_icone.create_app_icon()
        except ImportError:
            print("Aviso: script gerar_icone.py não encontrado. O EXE ficará sem ícone personalizado.")

    clean_previous_builds()
    
    # Compila o Gerador (Para o Cliente)
    build_exe("gerador_pedidos_pdf_ui.py", "Gerador_de_Pedidos")
    
    # Compila o Editor (Opcional, mas útil ter)
    build_exe("template_editor_ui.py", "Editor_de_Templates")
    
    organize_output()