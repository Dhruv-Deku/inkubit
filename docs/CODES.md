# Code lab: AI-designed error-correcting codes

Muse Spark (`muse-spark-1.3`) proposed stabilizer codes over 4 rounds of up to three per target, seeing every earlier verdict (`scripts/codes_bench.py`, `backend/qcanvas/codes.py`). Each code was checked exactly: commuting, independent generators, k = n - rank, and the distance d by brute force over every Pauli error from weight 1 up (dX, dZ: only X, only Z errors).

## Known codes, scored by the same checker

| Code | [[n,k,d]] | dX | dZ | CSS |
| --- | --- | --- | --- | --- |
| Five-qubit perfect code | [[5,1,3]] | 5 | 5 | no |
| Steane code | [[7,1,3]] | 3 | 3 | yes |
| Shor code | [[9,1,3]] | 3 | 3 | yes |
| Rotated surface code, d = 3 | [[9,1,3]] | 3 | 3 | yes |
| XZZX surface code, d = 3 | [[9,1,3]] | 3 | 3 | no |

## One logical qubit in 5 physical qubits

Aim: maximise the distance d (the code should correct any error on one qubit).

Best after each round: 3, 3, 3, 3 (d).

| Round | Code | Verdict |
| --- | --- | --- |
| 1 | `XZZXI IXZZX XIXZZ ZXIXZ` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 1 | `ZXXZI IZXXZ ZIZXX XZIZX` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 1 | `XYYXI IXYYX XIXYY YXIXY` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 2 | `YZZYI IYZZY YIYZZ ZYIYZ` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 2 | `ZZZXI IXZZX ZIXZZ XXIXZ` | valid [[5,1,3]], dX = 3, dZ = 3 |
| 2 | `YZZXI IXZZX YIXZZ ZXIXZ` | valid [[5,1,3]], dX = 3, dZ = 5 |
| 3 | `XZZXI IYZZX XIXZZ ZYIXZ` | valid [[5,1,3]], dX = 3, dZ = 5 |
| 3 | `XZZXI IXZZX XIYZZ ZXIXZ` | valid [[5,1,3]], dX = 3, dZ = 5 |
| 3 | `XZZYI IXZZX XIXZZ ZXIYZ` | valid [[5,1,3]], dX = 3, dZ = 5 |
| 4 | `YXXYI IYXXY YIYXX XYIYX` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 4 | `ZYYZI IZYYZ ZIZYY YZIZY` | valid [[5,1,3]], dX = 5, dZ = 5 |
| 4 | `XZZXI IXZZX XIXZZ YXXYI` | valid [[5,1,3]], dX = 5, dZ = 5 |

Best: `XZZXI IXZZX XIXZZ ZXIXZ`, valid [[5,1,3]], dX = 5, dZ = 5; idea: Cyclic XZZX pattern yields the perfect five-qubit code.

## A CSS code: 1 logical qubit in 7

Aim: maximise the distance d using only all-X and all-Z generators (a CSS code).

Best after each round: 3, 3, 3, 3 (d).

| Round | Code | Verdict |
| --- | --- | --- |
| 1 | `XXXXIII XXIIXXI XIXIXIX ZZZZIII ZZIIZZI ZIZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 1 | `IXXXIIX IXIIXXX XIXIXIX IZZZIIZ IZIIZZZ ZIZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 1 | `XXXIXII XXIXIXI XIXXIIX ZZZIZII ZZIZIZI ZIZZIIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 2 | `IIIXXXX IXXIIXX XIXIXIX IIIZZZZ IZZIIZZ ZIZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 2 | `XIIXXXI XXXIIXI XIXIXIX ZIIZZZI ZZZIIZI ZIZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 2 | `IXXXXII XIIXXIX XIXIXXI IZZZZII ZIIZZIZ ZIZIZZI` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 3 | `IIIXXXX XIXIIXX IXXIXIX IIIZZZZ ZIZIIZZ IZZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 3 | `XXXXIII IIXXIXX IXIXXIX ZZZZIII ZZIIZIZZ ZIZIZZIZ` | invalid: every generator must be 7 characters of I, X, Y, Z |
| 3 | `IXIXIXX IIXIXXX XIIXXIX ZIZIZIZZ ZZZIZZZZ ZIIZZIZ` | invalid: every generator must be 7 characters of I, X, Y, Z |
| 4 | `XXXXIII XXIIXIX XIXIXXI ZZZZIII ZZIIZIZ ZIZIZZI` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 4 | `XXIXXII XXXIIXI XIXIXIX ZZIZZII ZZZIIZI ZIZIZIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |
| 4 | `XIXXXII XXIIXXI XXXIIIX ZIZZZII ZZIIZZI ZZZIIIZ` | valid [[7,1,3]], dX = 3, dZ = 3, CSS |

Best: `XXXXIII XXIIXXI XIXIXIX ZZZZIII ZZIIZZI ZIZIZIZ`, valid [[7,1,3]], dX = 3, dZ = 3, CSS; idea: Steane CSS construction from the Hamming parity check gives balanced X and Z protection for distance 3.

## Biased noise: 1 logical qubit in 9

Aim: keep the distance d at least 3 and maximise dZ, the distance against Z errors alone (for hardware where phase flips are far more common than bit flips).

Best after each round: 3, 9, 9, 9 (dZ).

| Round | Code | Verdict |
| --- | --- | --- |
| 1 | `ZZIIIIIII IZZIIIIII IIIZZIIII IIIIZZIII IIIIIIZZI IIIIIIIZZ XXXXXXIII IIIXXXXXX` | valid [[9,1,3]], dX = 3, dZ = 3, CSS |
| 1 | `IIIXXXXII IXXIIXXII XIXIXIXII IIIZZZZII IZZIIZZII ZIZIZIZII IIIIIIIXX IIIIIIIZZ` | valid [[9,1,3]], dX = 3, dZ = 3, CSS |
| 1 | `XXIIIIIII IXXIIIIII IIIXXIIII IIIIXXIII IIIIIIXXI IIIIIIIXX ZZZZZZIII IIIZZZZZZ` | valid [[9,1,3]], dX = 3, dZ = 3, CSS |
| 2 | `YXIIIIIII IXYZZZZZZ ZZYXIIIII IIIXYZZZZ ZZZZYXIII IIIIIXYZZ ZZZZZZYXI IIIIIIIXY` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 2 | `XYZZZZZZZ ZYXIIIIII IIXYZZZZZ ZZZYXIIII IIIIXYZZZ ZZZZZYXII IIIIIIXYZ ZZZZZZZYX` | valid [[9,1,2]], dX = 9, dZ = 9 |
| 2 | `YXIIIIIII ZYXIIIIII IIXYZZZZZ IIIXYZZZZ ZZZZYXIII ZZZZZYXII IIIIIIXYZ IIIIIIIXY` | valid [[9,1,2]], dX = 3, dZ = 9 |
| 3 | `IYXIIIIII ZIXYZZZZZ IZZYXIIII ZIIIXYZZZ IZZZZYXII ZIIIIIXYZ IZZZZZZYX YIIIIIIIX` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 3 | `IIYXIIIII ZZIXYZZZZ IIZZYXIII ZZIIIXYZZ IIZZZZYXI ZZIIIIIXY XIZZZZZZY XYIIIIIII` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 3 | `IIIYXIIII ZZZIXYZZZ IIIZZYXII ZZZIIIXYZ IIIZZZZYX YZZIIIIIX YXIZZZZZZ IXYIIIIII` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 4 | `XIIIIIIIY XYZZZZZZI ZYXIIIIIZ IIXYZZZZI ZZZYXIIIZ IIIIXYZZI ZZZZZYXIZ IIIIIIXYI` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 4 | `IIIIIIIYX YZZZZZZIX YXIIIIIZZ IXYZZZZII ZZYXIIIZZ IIIXYZZII ZZZZYXIZZ IIIIIXYII` | valid [[9,1,3]], dX = 7, dZ = 9 |
| 4 | `IIIIIYXII ZZZZZIXYZ IIIIIZZYX YZZZZIIIX YXIIIZZZZ IXYZZIIII ZZYXIZZZZ IIIXYIIII` | valid [[9,1,3]], dX = 7, dZ = 9 |

Best: `YXIIIIIII IXYZZZZZZ ZZYXIIIII IIIXYZZZZ ZZZZYXIII IIIIIXYZZ ZZZZZZYXI IIIIIIIXY`, valid [[9,1,3]], dX = 7, dZ = 9; idea: Adjacent-pair X parts form a repetition code giving Z distance 9 while step-pattern Z parts keep X and Y checks distinct for overall distance 3.
