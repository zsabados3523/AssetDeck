"""Infraestrutura de internacionalização (i18n) do AssetDeck.

O idioma padrão e fonte de todas as strings é o Português do Brasil (pt-BR).
Traduções adicionais (como Inglês) são carregadas via QTranslator a partir
de arquivos .qm compilados na pasta translations/.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QCoreApplication, QTranslator

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "pt_BR"
SUPPORTED_LANGUAGES = {
    "pt_BR": "Português",
    "en": "English",
}

_installed_translator: QTranslator | None = None


class TrStr(str):
    """Subclasse de str que implementa o método .arg() do Qt.

    Permite converter f-strings para self.tr("... %1 ...").arg(x) mantendo
    compatibilidade completa com a API padrão de strings do Python e do Qt.
    """

    def arg(self, *values: object) -> TrStr:
        if not values:
            return self
        res = str(self)
        for val in values:
            matches = [int(m) for m in re.findall(r"%(\d+)", res)]
            if not matches:
                break
            lowest = min(matches)
            pattern = re.compile(rf"%{lowest}(?!\d)")
            m = pattern.search(res)
            if m:
                res = res[:m.start()] + str(val) + res[m.end():]
        return TrStr(res)


def _patch_qt_tr() -> None:
    """Garante que QObject.tr e QCoreApplication.translate retornem TrStr."""
    try:
        from PySide6.QtCore import QCoreApplication, QObject
    except ImportError:
        return

    _orig_translate = QCoreApplication.translate

    def _translate(context: str, sourceText: str, disambiguation: str = "", n: int = -1) -> TrStr:
        res = _orig_translate(context, sourceText, disambiguation, n)
        return TrStr(res)

    QCoreApplication.translate = staticmethod(_translate)

    def _tr(cls_or_self: object, sourceText: str, disambiguation: str = "", n: int = -1) -> TrStr:
        ctx = cls_or_self.__name__ if isinstance(cls_or_self, type) else cls_or_self.__class__.__name__
        return QCoreApplication.translate(ctx, sourceText, disambiguation, n)

    QObject.tr = _tr


_patch_qt_tr()


def get_translations_dir() -> Path:
    """Retorna o diretório onde os arquivos de tradução (.qm) estão armazenados."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_dir = Path(sys._MEIPASS) / "translations"
        if meipass_dir.exists():
            return meipass_dir

    repo_dir = Path(__file__).resolve().parent.parent / "translations"
    if repo_dir.exists():
        return repo_dir

    pkg_dir = Path(__file__).resolve().parent / "translations"
    return pkg_dir


def normalize_language(code: str | None) -> str:
    """Normaliza identificadores de idioma (ex.: 'pt-BR', 'en_US' -> 'pt_BR', 'en')."""
    if not code:
        return ""
    clean = code.strip().replace("-", "_").lower()
    if clean.startswith("pt"):
        return "pt_BR"
    if clean.startswith("en"):
        return "en"
    return code.strip()


def get_system_language() -> str:
    """Detecta o idioma do sistema operacional via QLocale."""
    try:
        from PySide6.QtCore import QLocale
        sys_code = QLocale.system().name()
        norm = normalize_language(sys_code)
        if norm in SUPPORTED_LANGUAGES:
            return norm
    except Exception as exc:
        log.warning("Falha ao consultar locale do sistema (%s); usando padrao.", exc)
    return DEFAULT_LANGUAGE


def get_effective_language(cfg: dict | None = None) -> str:
    """Resolve o idioma ativo: config salvo > locale do sistema > fallback pt-BR."""
    if cfg is None:
        try:
            from assetdeck import config
            cfg = config.load_config()
        except Exception as exc:
            log.warning("Nao consegui carregar config para i18n (%s).", exc)
            cfg = {}

    stored = cfg.get("language") if isinstance(cfg, dict) else None
    if stored:
        norm = normalize_language(str(stored))
        if norm in SUPPORTED_LANGUAGES:
            return norm
        log.warning("Idioma configurado %r nao suportado; usando fallback.", stored)
    return get_system_language()


def load_translator(lang: str, translations_dir: Path | None = None) -> QTranslator | None:
    """Carrega um QTranslator para o idioma especificado a partir do diretório de traduções."""
    norm = normalize_language(lang)
    if norm != "en":
        # Idioma fonte pt-BR não precisa de QTranslator
        return None

    try:
        from PySide6.QtCore import QTranslator
    except ImportError:
        return None

    tdir = translations_dir or get_translations_dir()
    qm_path = tdir / f"assetdeck_{norm}.qm"
    if not qm_path.exists():
        log.warning("Arquivo de traducao nao encontrado: %s", qm_path)
        return None

    translator = QTranslator()
    if translator.load(str(qm_path)):
        return translator

    log.warning("Falha ao carregar traducao de %s", qm_path)
    return None


def install_translator(app: QCoreApplication, lang: str | None = None) -> QTranslator | None:
    """Instala o QTranslator no QCoreApplication/QApplication antes de criar janelas."""
    global _installed_translator
    if _installed_translator is not None:
        app.removeTranslator(_installed_translator)
        _installed_translator = None

    effective_lang = normalize_language(lang) if lang else get_effective_language()
    translator = load_translator(effective_lang)
    if translator is not None:
        app.installTranslator(translator)
        _installed_translator = translator
        log.info("Traducao carregada para o idioma: %s", effective_lang)
    else:
        log.info("Usando idioma fonte (pt-BR): %s", effective_lang)
    return translator
