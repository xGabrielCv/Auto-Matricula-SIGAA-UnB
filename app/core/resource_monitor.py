"""
Monitor de recursos — seção 37 do pedido de continuação.

Só reporta o que consegue medir com confiança de verdade. Memória (RSS/
"working set") é medida via a API nativa do Windows (`ctypes`, sem
dependência nova). CPU por processo precisaria de duas amostras com um
intervalo entre elas para significar algo (não é instantâneo) — por isso
`medir_cpu_percentual` exige um `intervalo_seg` explícito e é sempre
opcional; se não for chamado, o app simplesmente não mostra CPU em vez de
inventar um número.

Em qualquer sistema que não seja Windows, ou se a chamada nativa falhar por
qualquer razão, as funções devolvem `None` — nunca um valor fabricado.

NOTA TÉCNICA (bug real encontrado em teste): as chamadas via
`ctypes.windll.<dll>.<funcao>(...)` sem `restype`/`argtypes` explícitos
falham silenciosamente em Windows 64-bit para funções que retornam/recebem
HANDLE (ponteiro de 64 bits) — o ctypes assume `c_int` (32 bits) por
padrão e trunca o valor, fazendo `GetProcessMemoryInfo` sempre retornar
falha. A correção é declarar os tipos explicitamente com `ctypes.wintypes`.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional


def _suportado() -> bool:
    return sys.platform == "win32"


def medir_memoria_mb() -> Optional[float]:
    """Memória "working set" (RSS) do processo atual, em MB. None se não for possível medir."""
    if not _suportado():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]

        handle = kernel32.GetCurrentProcess()
        contador = PROCESS_MEMORY_COUNTERS()
        contador.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(contador), contador.cb)
        if not ok:
            return None
        return contador.WorkingSetSize / (1024 * 1024)
    except Exception:
        return None


def _tempo_cpu_processo_seg() -> Optional[float]:
    """Soma do tempo de CPU (kernel+usuário) consumido pelo processo até agora, em segundos."""
    if not _suportado():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ]

        handle = kernel32.GetCurrentProcess()
        criacao, saida, kernel, usuario = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        ok = kernel32.GetProcessTimes(handle, ctypes.byref(criacao), ctypes.byref(saida), ctypes.byref(kernel), ctypes.byref(usuario))
        if not ok:
            return None

        def para_100ns(ft):
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        total_100ns = para_100ns(kernel) + para_100ns(usuario)
        return total_100ns / 10_000_000  # 100ns -> segundos
    except Exception:
        return None


def medir_cpu_percentual(intervalo_seg: float = 0.5) -> Optional[float]:
    """
    Mede o % de CPU usado pelo processo NO INTERVALO dado (bloqueia por
    `intervalo_seg`). Não chame isso de dentro de um loop de UI sem rodar
    numa thread separada — é deliberadamente bloqueante, como qualquer
    medição de CPU real precisa ser.
    """
    t0_wall = time.perf_counter()
    t0_cpu = _tempo_cpu_processo_seg()
    if t0_cpu is None:
        return None
    time.sleep(intervalo_seg)
    t1_wall = time.perf_counter()
    t1_cpu = _tempo_cpu_processo_seg()
    if t1_cpu is None:
        return None

    decorrido_wall = t1_wall - t0_wall
    decorrido_cpu = t1_cpu - t0_cpu
    if decorrido_wall <= 0:
        return None

    num_cpus = os.cpu_count() or 1
    return (decorrido_cpu / decorrido_wall / num_cpus) * 100


def resumo_recursos(medir_cpu: bool = False) -> dict:
    """Usado pelo diagnóstico/dashboard. `medir_cpu=True` bloqueia ~0.5s — só
    ative quando o usuário pedir explicitamente (botão), nunca automaticamente."""
    resultado = {
        "memoria_mb": medir_memoria_mb(),
        "cpu_percentual": None,
        "num_cpus_logicos": os.cpu_count(),
        "pid": os.getpid(),
    }
    if medir_cpu:
        resultado["cpu_percentual"] = medir_cpu_percentual()
    return resultado
