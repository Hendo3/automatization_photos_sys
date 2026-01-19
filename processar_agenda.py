import json
import logging
import shutil
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageOps

import config

logger = logging.getLogger(__name__)


def processar_pedidos_pdf_duas_paginas() -> None:
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
        with open(config.FILE_TEMPLATES_CONFIG, "r", encoding="utf-8") as f:
            templates = json.load(f)

        with open(config.FILE_PEDIDOS_DATA, "r", encoding="utf-8") as f:
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
        try:
            shutil.rmtree(config.DIR_TEMP)
        except Exception:
            pass
    config.DIR_TEMP.mkdir(parents=True, exist_ok=True)

    try:
        # === LOOP PRINCIPAL ===
        total = len(pedidos)
        for i, pedido in enumerate(pedidos):
            logger.info(f"--- Processando item {i + 1}/{total}: {pedido.get('output_pdf')} ---")

            # A. Valida PDF Base
            nome_pdf_base = pedido.get("input_pdf_base")
            if not nome_pdf_base:
                logger.error("Pedido sem 'input_pdf_base'. Pulando.")
                continue

            path_pdf_base = config.DIR_PDF / str(nome_pdf_base)
            if not path_pdf_base.exists():
                logger.error(f"PDF Base não encontrado na pasta input/pdf: {path_pdf_base}")
                continue

            # B. Rasteriza página 1 do PDF Base
            with fitz.open(path_pdf_base) as doc:
                if doc.page_count < 1:
                    logger.error(f"PDF Base sem páginas: {path_pdf_base}")
                    continue
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))  # 300 DPI

            temp_img_path = config.DIR_TEMP / f"temp_base_{i}.png"
            pix.save(str(temp_img_path))

            # C. Abre imagem para edição (RGBA para transparência)
            with Image.open(temp_img_path) as im:
                img_base = im.convert("RGBA")

            draw = ImageDraw.Draw(img_base)
            _page_w, _page_h = img_base.size

            # D. Coleta dados do Pedido
            dados_frente = pedido.get("pagina_frente", {}) or {}
            template_id = dados_frente.get("template_imagem")
            texto = dados_frente.get("texto", "") or ""
            fonte_override = dados_frente.get("fonte")
            tamanho_fonte_override = dados_frente.get("tamanho_fonte")

            # Dados de Imagem
            caminho_imagem_override = dados_frente.get("imagem_arquivo")
            caminho_imagem_auto = dados_frente.get("imagem_auto")
            is_full_page = bool(dados_frente.get("imagem_full_page", False))

            template = templates.get(template_id, {}) if template_id else {}

            def _apply_overlay(caminho_imagem: str | None):
                if not caminho_imagem:
                    return
                try:
                    p_img = Path(str(caminho_imagem))

                    # resolve relativo: tenta dentro de /pictures (mesma lógica do PDF base)
                    if not p_img.is_absolute():
                        candidate = config.DIR_PICTURES / p_img
                        if candidate.exists():
                            p_img = candidate

                    if p_img.exists():
                        with Image.open(p_img) as im_ov:
                            foto = im_ov.convert("RGBA")

                        page_w, page_h = img_base.size

                        if is_full_page:
                            foto = foto.resize((page_w, page_h), Image.Resampling.LANCZOS)
                            img_base.paste(foto, (0, 0), foto)
                        else:
                            px = template.get("photo_x") or template.get("img_x") or template.get("image_x")
                            py = template.get("photo_y") or template.get("img_y") or template.get("image_y")
                            pw = template.get("photo_w") or template.get("img_w") or template.get("image_w")
                            ph = template.get("photo_h") or template.get("img_h") or template.get("image_h")

                            if px is not None and py is not None:
                                if pw and ph:
                                    foto = ImageOps.fit(foto, (int(pw), int(ph)), centering=(0.5, 0.5))
                                dest_x, dest_y = int(px), int(py)
                            else:
                                target_w = int(page_w * 0.5)
                                ratio = target_w / float(foto.width)
                                target_h = int(foto.height * ratio)
                                foto = foto.resize((target_w, target_h), Image.Resampling.LANCZOS)
                                dest_x = (page_w - target_w) // 2
                                dest_y = (page_h - target_h) // 2

                            img_base.paste(foto, (dest_x, dest_y), foto)
                    else:
                        logger.warning(f"Imagem overlay não encontrada: {p_img}")
                except Exception as e:
                    logger.error(f"Erro ao aplicar overlay de imagem: {e}")

            # === LÓGICA 1: PROCESSAMENTO DE IMAGEM (auto picture) ===
            _apply_overlay(caminho_imagem_auto)

            # === LÓGICA 2: PROCESSAMENTO DE TEXTO ===
            if texto and template:
                try:
                    # fonte: override -> template[DEFAULT_FONT] -> FALLBACK_FONT
                    if fonte_override and fonte_override != "(Padrão do Template)":
                        nome_fonte = str(fonte_override)
                    else:
                        key = getattr(config, "DEFAULT_FONT", "font_name")
                        nome_fonte = (template.get(key) or "").strip() or config.FALLBACK_FONT

                    path_fonte = config.DIR_FONTS / str(nome_fonte)
                    if not path_fonte.exists():
                        fb = config.DIR_FONTS / config.FALLBACK_FONT
                        if fb.exists():
                            path_fonte = fb

                    # Decide tamanho final (template -> override)
                    t_size = template.get("font_size", 50)
                    if tamanho_fonte_override is not None:
                        try:
                            t_size = int(float(tamanho_fonte_override))
                        except Exception:
                            pass

                    try:
                        font = ImageFont.truetype(str(path_fonte), int(t_size))
                    except Exception:
                        font = ImageFont.load_default()

                    col = template.get("color", "#000000")
                    align = template.get("align", "left")
                    max_w = template.get("max_width_pixels", 1000)
                    pos_x = template.get("pos_x", 0)
                    pos_y = template.get("pos_y", 0)

                    # Quebra de linha (Word Wrap)
                    words = texto.split()
                    lines: list[str] = []
                    current_line = ""
                    for word in words:
                        test_line = f"{current_line} {word}".strip()
                        bbox = draw.textbbox((0, 0), test_line, font=font)
                        if (bbox[2] - bbox[0]) <= max_w:
                            current_line = test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = word
                    if current_line:
                        lines.append(current_line)

                    # Renderiza Linhas
                    getmetrics = getattr(font, "getmetrics", None)
                    if callable(getmetrics):
                        metrics = getmetrics()
                        if isinstance(metrics, (tuple, list)) and len(metrics) >= 2:
                            ascent, descent = metrics[:2]
                            line_height = (ascent + descent) * 1.2
                        else:
                            bbox = draw.textbbox((0, 0), "Ag", font=font)
                            line_height = (bbox[3] - bbox[1]) * 1.2
                    else:
                        bbox = draw.textbbox((0, 0), "Ag", font=font)
                        line_height = (bbox[3] - bbox[1]) * 1.2

                    current_y = pos_y
                    for line in lines:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        w_line = bbox[2] - bbox[0]

                        dx = pos_x
                        if align == "center":
                            dx += (max_w / 2) - (w_line / 2)
                        elif align == "right":
                            dx += max_w - w_line

                        draw.text((dx, current_y), line, font=font, fill=col)
                        current_y += line_height

                except Exception as e:
                    logger.error(f"Erro ao desenhar texto: {e}")

            # === LÓGICA 3: PROCESSAMENTO DE IMAGEM (override/manual) ===
            _apply_overlay(caminho_imagem_override)

            # E. Salva Resultado
            final_img = img_base.convert("RGB")
            output_filename = pedido.get("output_pdf", f"pedido_{i}.pdf") or f"pedido_{i}.pdf"
            if not str(output_filename).lower().endswith(".pdf"):
                output_filename = f"{output_filename}.pdf"

            output_path = config.DIR_OUTPUT / str(output_filename)
            final_img.save(output_path, "PDF", resolution=300.0)
            logger.info(f"✔ Arquivo Gerado: {output_path}")

    except Exception as e:
        logger.critical(f"ERRO GERAL NO PROCESSAMENTO: {e}")

    finally:
        # Limpeza
        if config.DIR_TEMP.exists():
            try:
                shutil.rmtree(config.DIR_TEMP)
            except Exception:
                pass
        logger.info(">>> FIM DO PROCESSAMENTO <<<")


if __name__ == "__main__":
    processar_pedidos_pdf_duas_paginas()