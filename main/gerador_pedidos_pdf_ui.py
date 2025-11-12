
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
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures" # Onde os PDFs base estão
OUTPUT_JSON_FILE = BASE_DIR / "pedidos_pdf_duas_paginas.json" # O JSON que será gerado

# --- Carregar Configs, Fontes e PDFs Base ---
TEMPLATES_CONFIG = {}
try:
    with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        TEMPLATES_CONFIG = json.load(f)
    logger.info(f"Carregados {len(TEMPLATES_CONFIG)} templates de '{TEMPLATE_CONFIG_FILE}'")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO ao carregar 'templates.json': {e}")

AVAILABLE_FONTS = [""] # Opção para não usar override
try:
    for font_file in FONT_DIR.iterdir():
        if font_file.is_file() and (font_file.suffix.lower() == ".ttf" or font_file.suffix.lower() == ".otf"):
            AVAILABLE_FONTS.append(font_file.name)
    AVAILABLE_FONTS.sort()
except Exception as e:
    logger.warning(f"Não foi possível listar fontes em '{FONT_DIR}': {e}")

AVAILABLE_BASE_PDFS = []
try:
    AVAILABLE_BASE_PDFS = sorted([f.name for f in PICTURE_DIR.iterdir() if f.suffix.lower() == '.pdf'])
    if not AVAILABLE_BASE_PDFS:
        AVAILABLE_BASE_PDFS = ["(Nenhum PDF encontrado em /pictures)"]
except FileNotFoundError:
    logger.warning(f"Pasta de PDFs base '{PICTURE_DIR}' não encontrada.")
    AVAILABLE_BASE_PDFS = ["(Nenhuma pasta /pictures)"]

# --- Configuração da UI ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class PedidoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerador de Pedidos (PDF-para-PDF)")
        self.geometry("800x600")

        # Variáveis de estado da UI
        self.output_pdf_var = ctk.StringVar(value="")
        self.input_pdf_var = ctk.StringVar(value=AVAILABLE_BASE_PDFS[0])
        self.template_id_var = ctk.StringVar(value=list(TEMPLATES_CONFIG.keys())[0] if TEMPLATES_CONFIG else "")
        self.text_var = ctk.StringVar(value="")
        self.font_override_var = ctk.StringVar(value=AVAILABLE_FONTS[0])

        self.pedidos_em_lote = [] # Lista de pedidos a serem gerados

        self._setup_ui()

    def _setup_ui(self):
        # Frame principal para o formulário
        self.form_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.form_frame.pack(padx=20, pady=10, fill="x")
        self.form_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self.form_frame, text="Novo Pedido (PDF-para-PDF)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=10)

        # --- Linha 1: Nome do PDF de Saída ---
        ctk.CTkLabel(self.form_frame, text="1. Nome do PDF de Saída:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkEntry(self.form_frame, textvariable=self.output_pdf_var, placeholder_text="ex: pedido_cliente_jose.pdf").grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # --- Linha 2: PDF Base de Entrada ---
        ctk.CTkLabel(self.form_frame, text="2. PDF Base de 2 Páginas:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkOptionMenu(self.form_frame, variable=self.input_pdf_var, values=AVAILABLE_BASE_PDFS).grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # --- Linha 3: Template ID (da Capa) ---
        ctk.CTkLabel(self.form_frame, text="3. Template da Capa (ID):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        template_keys = list(TEMPLATES_CONFIG.keys()) if TEMPLATES_CONFIG else ["(Nenhum template salvo)"]
        ctk.CTkOptionMenu(self.form_frame, variable=self.template_id_var, values=template_keys).grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # --- Linha 4: Texto Personalizado ---
        ctk.CTkLabel(self.form_frame, text="4. Texto Personalizado:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkEntry(self.form_frame, textvariable=self.text_var, placeholder_text="ex: Ana Clara Silva").grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        # --- Linha 5: Fonte Override (Opcional) ---
        ctk.CTkLabel(self.form_frame, text="5. Fonte Override (opcional):").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkOptionMenu(self.form_frame, variable=self.font_override_var, values=AVAILABLE_FONTS).grid(row=5, column=1, padx=5, pady=5, sticky="ew")

        # --- Botão para Adicionar Pedido ---
        self.add_pedido_button = ctk.CTkButton(self.form_frame, text="Adicionar Pedido ao Lote", command=self._add_pedido)
        self.add_pedido_button.grid(row=6, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # --- Lista de Pedidos Adicionados ---
        ctk.CTkLabel(self, text="Lote de Pedidos a Gerar:").pack(padx=20, pady=(10,0), anchor="w")
        self.pedidos_list_frame = ctk.CTkScrollableFrame(self, height=200)
        self.pedidos_list_frame.pack(padx=20, pady=10, fill="x", expand=True)
        self.update_pedidos_list_display()

        # --- Botão para Gerar o JSON Final ---
        self.generate_json_button = ctk.CTkButton(self, text="GERAR ARQUIVO JSON DE PEDIDOS", command=self._generate_final_json)
        self.generate_json_button.pack(padx=20, pady=20, fill="x")

    def _add_pedido(self):
        output_pdf = self.output_pdf_var.get().strip()
        input_pdf = self.input_pdf_var.get()
        template_id = self.template_id_var.get()
        texto = self.text_var.get() # Texto vazio é permitido (para não adicionar texto)
        font_override = self.font_override_var.get()

        if not output_pdf or input_pdf.startswith("(") or template_id.startswith("("):
            messagebox.showwarning("Erro", "Por favor, preencha o Nome do PDF, selecione um PDF Base e um Template ID.")
            return

        # Monta o pedido no formato do 'pedidos_pdf_duas_paginas.json'
        pedido_data = {
            "output_pdf": output_pdf + (".pdf" if not output_pdf.endswith(".pdf") else ""),
            "input_pdf_base": input_pdf,
            "pagina_frente": {
                "template_imagem": template_id,
                "texto": texto,
                "fonte": font_override if font_override else None
            }
        }

        self.pedidos_em_lote.append(pedido_data)
        logger.info(f"Pedido adicionado ao lote: {output_pdf}")
        self.update_pedidos_list_display()

        # Limpa os campos para o próximo pedido
        self.output_pdf_var.set("")
        self.text_var.set("")

    def update_pedidos_list_display(self):
        # Limpa o frame
        for widget in self.pedidos_list_frame.winfo_children():
            widget.destroy()

        if not self.pedidos_em_lote:
            ctk.CTkLabel(self.pedidos_list_frame, text="Nenhum pedido adicionado ao lote.").pack(padx=10, pady=5)
            return

        for i, pedido in enumerate(self.pedidos_em_lote):
            text_display = (f"Pedido {i+1}: {pedido['output_pdf']} "
                            f"(Base: {pedido['input_pdf_base']}, "
                            f"Texto: '{pedido['pagina_frente']['texto']}')")
            
            ctk.CTkLabel(self.pedidos_list_frame, text=text_display, anchor="w").pack(padx=10, pady=2, fill="x")

    def _generate_final_json(self):
        if not self.pedidos_em_lote:
            messagebox.showwarning("Erro", "Nenhum pedido foi adicionado ao lote.")
            return

        try:
            with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pedidos_em_lote, f, indent=2, ensure_ascii=False)
            logger.info(f"Arquivo JSON final gerado com sucesso em: {OUTPUT_JSON_FILE}")
            messagebox.showinfo("Sucesso", f"Arquivo '{OUTPUT_JSON_FILE}' gerado com sucesso!")
            # Limpa a lista após gerar
            self.pedidos_em_lote = []
            self.update_pedidos_list_display()
        except Exception as e:
            logger.error(f"Erro ao gerar o arquivo JSON final: {e}")
            messagebox.showerror("Erro", f"Erro ao gerar o JSON: {e}")

if __name__ == "__main__":
    app = PedidoApp()
    app.mainloop()