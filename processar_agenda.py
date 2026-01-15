import json
import logging
import shutil
from pathlib import Path

# --- IMPORTANTE: Traz as configurações de caminhos do config.py ---
import config
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Configura logger
logger = logging.getLogger(__name__)

def processar_pedidos_pdf_duas_paginas():
    """
    Motor de processamento PDF.
    - Lê configurações do config.py (NÃO USA CAMINHOS RELATIVOS AQUI)
    - Suporta: Texto, Imagens (Overlay) e Full Page.
    """
    
    logger.info(">>> INICIANDO MOTOR DE PROCESSAMENTO <<<")
    
    # 1. Validação de Arquivos Essenciais (Prova Real)
    logger.info(f">>> Procurando Templates em: {config.FILE_TEMPLATES_CONFIG}")
    if not config.FILE_TEMPLATES_CONFIG.exists():
        logger.critical(f"ERRO FATAL: Arquivo de templates não existe: {config.FILE_TEMPLATES_CONFIG}")
        return
        
    logger.info(f">>> Procurando Pedidos em: {config.FILE_PEDIDOS_DATA}")
    if not config.FILE_PEDIDOS_DATA.exists():
        logger.critical(f"ERRO FATAL: Arquivo de pedidos não existe: {config.FILE_PEDIDOS_DATA}")
        return

    # 2. Carregamento dos JSONs
    try:
        with open(config.FILE_TEMPLATES_CONFIG, 'r', encoding='utf-8') as f:
            templates = json.load(f)
            
        with open(config.FILE_PEDIDOS_DATA, 'r', encoding='utf-8') as f:
            pedidos = json.load(f)
    except Exception as e:
        logger.critical(f"ERRO ao ler JSON: {e}")
        return

    if not pedidos:
        logger.warning("A lista de pedidos está vazia. Nada a fazer.")
        return

    # 3. Preparação do Ambiente
    config.ensure_directories()
    
    # Limpa pasta temporária anterior (se houver) e recria
    if config.DIR_TEMP.exists():
        try: shutil.rmtree(config.DIR_TEMP)
        except: pass
    config.DIR_TEMP.mkdir(parents=True, exist_ok=True)

    try:
        # === LOOP PRINCIPAL ===
        total = len(pedidos)
        for i, pedido in enumerate(pedidos):
            logger.info(f"--- Processando item {i+1}/{total}: {pedido.get('output_pdf')} ---")
            
            # A. Valida PDF Base
            nome_pdf_base = pedido.get("input_pdf_base")
            path_pdf_base = config.DIR_PICTURES / nome_pdf_base
            
            if not path_pdf_base.exists():
                logger.error(f"PDF Base não encontrado na pasta pictures: {path_pdf_base}")
                continue

            # B. Rasteriza página 1 do PDF Base
            doc = fitz.open(path_pdf_base)
            page = doc[0] 
            # 300 DPI para qualidade
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            
            temp_img_path = config.DIR_TEMP / f"temp_base_{i}.png"
            pix.save(str(temp_img_path))
            doc.close()

            # C. Abre imagem para edição (RGBA para transparência)
            img_base = Image.open(temp_img_path).convert("RGBA")
            draw = ImageDraw.Draw(img_base)
            page_w, page_h = img_base.size

            # D. Coleta dados do Pedido
            dados_frente = pedido.get("pagina_frente", {})
            template_id = dados_frente.get("template_imagem")
            texto = dados_frente.get("texto", "")
            fonte_override = dados_frente.get("fonte")
            
            # Dados de Imagem
            caminho_imagem = dados_frente.get("imagem_arquivo")
            is_full_page = dados_frente.get("imagem_full_page", False)

            template = templates.get(template_id, {})

            # === LÓGICA 1: PROCESSAMENTO DE IMAGEM (OVERLAY) ===
            if caminho_imagem:
                try:
                    # O caminho vem absoluto do seletor de arquivos da UI
                    path_img = Path(caminho_imagem)
                    
                    if path_img.exists():
                        overlay = Image.open(path_img).convert("RGBA")
                        
                        if is_full_page:
                            # >>> MODO 100% (FULL PAGE) <<<
                            logger.debug(f"Aplicando imagem Full Page: {path_img.name}")
                            overlay = overlay.resize((page_w, page_h), Image.Resampling.LANCZOS)
                            img_base.paste(overlay, (0, 0), overlay)
                        
                        else:
                            # >>> MODO COORDENADAS OU FALLBACK <<<
                            px = template.get("photo_x") or template.get("img_x") or template.get("image_x")
                            py = template.get("photo_y") or template.get("img_y") or template.get("image_y")
                            pw = template.get("photo_w") or template.get("img_w") or template.get("image_w")
                            ph = template.get("photo_h") or template.get("img_h") or template.get("image_h")

                            if px is not None and py is not None:
                                # Template define posição
                                if pw and ph:
                                    overlay = ImageOps.fit(overlay, (int(pw), int(ph)), centering=(0.5, 0.5))
                                img_base.paste(overlay, (int(px), int(py)), overlay)
                            else:
                                # Sem posição definida -> Centraliza (50% largura)
                                logger.debug("Sem coordenadas no template. Usando centralização (Fallback).")
                                target_w = int(page_w * 0.5)
                                ratio = target_w / float(overlay.width)
                                target_h = int(overlay.height * ratio)
                                overlay = overlay.resize((target_w, target_h), Image.Resampling.LANCZOS)
                                
                                dx = (page_w - target_w) // 2
                                dy = (page_h - target_h) // 2
                                img_base.paste(overlay, (dx, dy), overlay)
                    else:
                        logger.warning(f"Arquivo de imagem não acessível: {caminho_imagem}")
                except Exception as e:
                    logger.error(f"Erro ao processar imagem overlay: {e}")

            # === LÓGICA 2: PROCESSAMENTO DE TEXTO ===
            if texto and template:
                try:
                    nome_fonte = fonte_override if (fonte_override and fonte_override != "(Padrão do Template)") else template.get("font_name", config.DEFAULT_FONT_NAME)
                    path_fonte = config.DIR_FONTS / nome_fonte
                    
                    # Fallback de fonte se não achar
                    if not path_fonte.exists(): 
                        path_fonte = config.DIR_FONTS / config.DEFAULT_FONT_NAME
                    
                    t_size = template.get("font_size", 50)
                    try:
                        font = ImageFont.truetype(str(path_fonte), t_size)
                    except:
                        # Último recurso se a fonte padrão falhar
                        font = ImageFont.load_default()

                    col = template.get("color", "#000000")
                    align = template.get("align", "left")
                    max_w = template.get("max_width_pixels", 1000)
                    pos_x = template.get("pos_x", 0)
                    pos_y = template.get("pos_y", 0)

                    # Quebra de linha (Word Wrap)
                    words = texto.split()
                    lines = []
                    current_line = ""
                    for word in words:
                        test_line = f"{current_line} {word}".strip()
                        bbox = draw.textbbox((0, 0), test_line, font=font)
                        if (bbox[2] - bbox[0]) <= max_w:
                            current_line = test_line
                        else:
                            lines.append(current_line)
                            current_line = word
                    lines.append(current_line)

                    # Renderiza Linhas
                    ascent, descent = font.getmetrics()
                    line_height = (ascent + descent) * 1.2
                    current_y = pos_y

                    for line in lines:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        w_line = bbox[2] - bbox[0]
                        dx = pos_x
                        if align == "center": dx += (max_w / 2) - (w_line / 2)
                        elif align == "right": dx += max_w - w_line
                        
                        draw.text((dx, current_y), line, font=font, fill=col)
                        current_y += line_height

                except Exception as e:
                    logger.error(f"Erro ao desenhar texto: {e}")

            # E. Salva Resultado
            final_img = img_base.convert("RGB")
            output_filename = pedido.get("output_pdf", f"pedido_{i}.pdf")
            if not output_filename.lower().endswith(".pdf"): output_filename += ".pdf"
            
            output_path = config.DIR_OUTPUT / output_filename
            final_img.save(output_path, "PDF", resolution=300.0)
            logger.info(f"✔ Arquivo Gerado: {output_path}")

    except Exception as e:
        logger.critical(f"ERRO GERAL NO PROCESSAMENTO: {e}")
    
    finally:
        # Limpeza
        if config.DIR_TEMP.exists():
            try: shutil.rmtree(config.DIR_TEMP)
            except: pass
        logger.info(">>> FIM DO PROCESSAMENTO <<<")

if __name__ == "__main__":
    processar_pedidos_pdf_duas_paginas()