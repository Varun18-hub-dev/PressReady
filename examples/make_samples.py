"""Write the two sample jobs to disk.

    python examples/make_samples.py [out_dir]   # good_job.pdf, bad_job.pdf
"""

import sys
from pathlib import Path

from pressready.samples import make_bad, make_good

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    out.mkdir(parents=True, exist_ok=True)
    print(make_good(out / "good_job.pdf"))
    print(make_bad(out / "bad_job.pdf"))
