# Niederer Slab Data

This folder contains the tracked release example dataset used by
`examples/niederer/main.qmd`.

Source:

- Niederer et al. cardiac electrophysiology slab verification case
- Local source case used for export on the maintainer machine:
  `/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials/NiedererEtAl2011/NiedererEtAl2011verification/Niederer.foam`

Dataset shape:

- 8 timesteps
- Surface-only export
- 11,052 points / 11,050 cells per frame
- Fields preserved: `Vm`, `activationTime`, `ionicCurrent`, `Jsi`,
  `externalStimulusCurrent`

Export command used to generate the committed files:

```bash
python3 scripts/export_niederer_example.py \
  /Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials/NiedererEtAl2011/NiedererEtAl2011verification/Niederer.foam \
  examples/niederer/data/niederer
```

The series index must keep the `.vtk.series` suffix because 4Dpapers format
detection keys off that filename ending even though the individual frames are
stored as `.vtp`.
