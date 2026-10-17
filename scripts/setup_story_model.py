"""Explicit free model download; runtime never downloads or calls hosted inference."""
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings


def memory():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    ctypes.windll.psapi.GetProcessMemoryInfo(process(), ctypes.byref(counters), counters.cb)
    return {'working_set_MB': round(counters.WorkingSetSize/1e6, 1), 'peak_working_set_MB': round(counters.PeakWorkingSetSize/1e6, 1)}


if __name__ == '__main__':
    settings = Settings(_env_file=None)
    print('Model: ' + settings.story_embedding_model + '; Apache-2.0; CPU only.', flush=True)
    print('Cache outside Git: ' + settings.story_model_cache, flush=True)
    start = perf_counter()
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(4)
    model = SentenceTransformer(settings.story_embedding_model, device='cpu',
                               cache_folder=settings.story_model_cache, trust_remote_code=False)
    loaded = perf_counter()
    vectors = model.encode(['A satellite enters lunar orbit.', 'A spacecraft reaches orbit around the moon.'],
                           normalize_embeddings=True, batch_size=24)
    print(json.dumps({'download_and_load_seconds': round(loaded-start, 3),
                      'batch_seconds': round(perf_counter()-loaded, 3), 'dimensions': vectors.shape[1],
                      'similarity': float(vectors[0] @ vectors[1]), **memory()}), flush=True)
