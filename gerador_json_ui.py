import customtkinter as ctk
import json
from pathlib import Path
import logging
from tkinter import messagebox

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Definição de Caminhos ---
BASE_DIR = Path(__file__).parent
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"
FONT_DIR = BASE_DIR / "fonts" # Para listar as fontes disponíveis
OUTPUT_JSON_FILE = BASE_DIR / "pedidos_para_pdf.json" # O JSON que será gerado

# --- Carregar Configuração de Templates ---
TEMPLATES_CONFIG = {}
try:
    with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        TEMPLATES_CONFIG = json.load(f)
    logger.info(f"Carregados {len(TEMPLATES_CONFIG)} templates de '{TEMPLATE_CONFIG_FILE}'")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO ao carregar 'templates.json': {e}")

# --- Obter Fontes Disponíveis ---
AVAILABLE_FONTS = [""] # Opção para não usar override
try:
    for font_file in FONT_DIR.iterdir():
        if font_file.is_file() and (font_file.suffix.lower() == ".ttf" or font_file.suffix.lower() == ".otf"):
            AVAILABLE_FONTS.append(font_file.name)
    AVAILABLE_FONTS.sort() # Ordena as fontes
except Exception as e:
    logger.warning(f"Não foi possível listar fontes em '{FONT_DIR}': {e}. Usando apenas fontes padrão.")

# --- Configuração da UI ---
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerador de JSON de Pedidos PDF")
        self.geometry("800x600")

        # Variáveis de estado da UI
        self.current_pdf_id = ctk.StringVar(value="")
        self.current_template = ctk.StringVar(value="")
        self.current_text = ctk.StringVar(value="")
        self.current_font_override = ctk.StringVar(value="")

        self.pedidos_globais = [] # Lista final de PDFs a serem gerados
        self.paginas_do_pdf_atual = [] # Páginas para o PDF que está sendo montado

        self._setup_ui()

    def _setup_ui(self):
        # Frame principal para o formulário
        self.form_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.form_frame.pack(padx=20, pady=10, fill="x")
        self.form_frame.columnconfigure(1, weight=1) # Faz a segunda coluna expandir

        # --- Linha 1: ID do PDF (Nome do Arquivo Final) ---
        ctk.CTkLabel(self.form_frame, text="Nome do PDF (Ex: 'pedido_123.pdf'):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkEntry(self.form_frame, textvariable=self.current_pdf_id).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # --- Separador ---
        ctk.CTkFrame(self.form_frame, height=2, fg_color="gray").grid(row=1, column=0, columnspan=2, pady=10, sticky="ew")
        
        # --- Linha 2: Template da Imagem ---
        ctk.CTkLabel(self.form_frame, text="1. Template da Imagem:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        template_options = list(TEMPLATES_CONFIG.keys())
        if not template_options:
            template_options = ["(Nenhum template encontrado)"]
            self.current_template.set(template_options[0])
        else:
            self.current_template.set(template_options[0]) # Seleciona o primeiro por padrão

        ctk.CTkOptionMenu(self.form_frame, variable=self.current_template, values=template_options).grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # --- Linha 3: Texto Personalizado ---
        ctk.CTkLabel(self.form_frame, text="2. Texto Personalizado:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkEntry(self.form_frame, textvariable=self.current_text).grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # --- Linha 4: Fonte Override (Opcional) ---
        ctk.CTkLabel(self.form_frame, text="3. Fonte Override (opcional):").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.current_font_override.set(AVAILABLE_FONTS[0]) # Define o primeiro item (vazio)
        ctk.CTkOptionMenu(self.form_frame, variable=self.current_font_override, values=AVAILABLE_FONTS).grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        # --- Botão para Adicionar Página ---
        self.add_page_button = ctk.CTkButton(self.form_frame, text="Adicionar Página ao PDF Atual", command=self._add_page)
        self.add_page_button.grid(row=5, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # --- Lista de Páginas Adicionadas (para o PDF atual) ---
        ctk.CTkLabel(self, text="Páginas no PDF Atual:").pack(padx=20, pady=(10,0), anchor="w")
        self.pages_list_frame = ctk.CTkScrollableFrame(self, height=150)
        self.pages_list_frame.pack(padx=20, pady=10, fill="x", expand=True)
        self.update_pages_list_display()

        # --- Botão para Concluir PDF e Reiniciar ---
        self.finish_pdf_button = ctk.CTkButton(self, text="Concluir PDF e Iniciar Novo", command=self._finish_pdf)
        self.finish_pdf_button.pack(padx=20, pady=(0,10), fill="x")

        # --- Botão para Gerar o JSON Final ---
        self.generate_json_button = ctk.CTkButton(self, text="GERAR ARQUIVO JSON FINAL", command=self._generate_final_json)
        self.generate_json_button.pack(padx=20, pady=20, fill="x")

    def _add_page(self):
        template = self.current_template.get()
        text = self.current_text.get()
        font_override = self.current_font_override.get()
        if not template or not text:
            messagebox.showwarning("Erro", "Por favor, selecione um template e digite o texto.")
            return
            return

        page_data = {
            "imagem": template,
            "texto": text
        }
        if font_override: # Só adiciona se houver um override
            page_data["fonte"] = font_override

        self.paginas_do_pdf_atual.append(page_data)
        logger.info(f"Página adicionada: {page_data}")
        self.update_pages_list_display()

        # Limpa os campos para a próxima página, mantém o PDF ID
        self.current_template.set(list(TEMPLATES_CONFIG.keys())[0] if TEMPLATES_CONFIG else "")
        self.current_text.set("")
        self.current_font_override.set(AVAILABLE_FONTS[0])

    def update_pages_list_display(self):
        # Limpa o frame para redesenhar
        for widget in self.pages_list_frame.winfo_children():
            widget.destroy()

        if not self.paginas_do_pdf_atual:
            ctk.CTkLabel(self.pages_list_frame, text="Nenhuma página adicionada ainda para este PDF.").pack(padx=10, pady=5)
            return

        for i, page in enumerate(self.paginas_do_pdf_atual):
            text_display = f"Página {i+1}: '{page['texto']}' (Img: {page['imagem']}"
            if page.get('fonte'):
                text_display += f", Fonte: {page['fonte']})"
            else:
                text_display += ")"
            
            ctk.CTkLabel(self.pages_list_frame, text=text_display, anchor="w").pack(padx=10, pady=2, fill="x")
    def _finish_pdf(self):
        pdf_id = self.current_pdf_id.get().strip()
        if not pdf_id:
            messagebox.showwarning("Erro", "Por favor, insira um nome para o PDF.")
            return
        
        if not self.paginas_do_pdf_atual:
            messagebox.showwarning("Erro", "Por favor, adicione pelo menos uma página ao PDF.")
            return
            return

        # Adiciona a entrada do PDF completo à lista global
        self.pedidos_globais.append({
            "output_pdf": pdf_id + (".pdf" if not pdf_id.endswith(".pdf") else ""), # Garante .pdf
            "paginas": self.paginas_do_pdf_atual
        })
        logger.info(f"PDF '{pdf_id}' adicionado à lista global. Contém {len(self.paginas_do_pdf_atual)} páginas.")

        # Reinicia para o próximo PDF
        self.paginas_do_pdf_atual = []
        self.current_pdf_id.set("")
        self.current_template.set(list(TEMPLATES_CONFIG.keys())[0] if TEMPLATES_CONFIG else "")
        self.current_text.set("")
        self.current_font_override.set(AVAILABLE_FONTS[0])
        self.update_pages_list_display()
        messagebox.showinfo("Sucesso", f"PDF '{pdf_id}' adicionado. Pronto para o próximo.")

    def _generate_final_json(self):
        if not self.pedidos_globais:
            messagebox.showwarning("Erro", "Nenhum pedido de PDF foi adicionado para gerar o JSON.")
            return

        try:
            with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pedidos_globais, f, indent=2, ensure_ascii=False)
            logger.info(f"Arquivo JSON final gerado com sucesso em: {OUTPUT_JSON_FILE}")
            messagebox.showinfo("Sucesso", f"Arquivo '{OUTPUT_JSON_FILE}' gerado com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao gerar o arquivo JSON final: {e}")
            messagebox.showerror("Erro", f"Erro ao gerar o JSON: {e}")
if __name__ == "__main__":
    app = App()
    app.mainloop()