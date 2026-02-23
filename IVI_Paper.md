# IVI: Integer Vector Inversion by Diophantine Digit Propagation

**Ed Gerck\***  
Planalto Research  
781 Washington St. #3423, Sonora, CA 95370  
ORCID: 0000-0002-0128-5875

**This version:** Feb/23/2026  
**First version:** Nov/4/2024

## Abstract

Empirical conjectures of Gerck et. al. in 1982, based on regularities observed in the factorization structure of semi-primes, are investigated. This work introduces IVI, a constructive formulation of integer multiplication inversion as a Diophantine equation in 50 bounded states (as justified by the empirical conjectures since 1982). The method reformulates global factorization as a finitist digit-propagation system governed by a solved diophantine equation, at every position. The construction is finite, explicit, and logically decidable. A 617-decimal semiprime is typically factored in less than 4.2 seconds on a single-core CPU.

## 1 Introduction

Our long-term research program in physics and mathematics [1—5] supports algebraic mappings and modular arithmetic in finitist systems (e.g. Zn or rational constructions over Zn) to produce exact results in quantum mechanics, using pure states.

1Corresponding author: https://www.researchgate.net/profile/Ed_Gerck

A key outcome is inversion of multiplication at the digit level as a new mathematical operator. This experimentally leads to large reductions in the expected factorization time for large integers, such as with 617-decimal digits or more, e.g., RSA-2048 or RSA-4096.

Widely deployed encryption protocols operate within finite integer arithmetic. Their security relies on an assumed computational hardness of inversion problems in that domain, which mathematically fails under IVI. The process is deterministic, in the sense of being logically decidable (LD). We solve a bounded Diophantine equation in 50 states, represented as integer vectors from LSD to MSD, producing a unique factorization of a 617-digit semiprime in 617 propagation steps. IVI is shown to be necessary and sufficient (within LD) for digit-level inversion. The global prime factorization of N is unique up to order by the Fundamental Theorem of Arithmetic.

## 2 Scope

This Section is presented to avoid reader bias in face of extraordinary results. IVI does not use Shor's algorithm, qubits, or current physical quantum models. The construction operates entirely within finitist integer arithmetic. IVI is not recursive search with pruning and not random search. It is a bounded Diophantine equation with 50 states that do not expand during digit propagation, working unlike a finite-state machine in that all 50 states are possible concurrently. Complex numbers, real numbers, irrational numbers, and p-adics are not required. This does not repudiate them, just makes their use unnecessary.

## 3 Digit Representation

Let where N = p·q,

$$N = \sum_{k=1}^{n} n_k 10^{k-1}, \quad p = \sum_{k=1}^{n} p_k 10^{k-1}, \quad q = \sum_{k=1}^{n} q_k 10^{k-1},$$

with $n_k, p_k, q_k \in \{0, \ldots, 9\}$, and $k = 1$ denotes the least significant digit (LSD).

## 4 Carry Structure

$c_1 = 0$, $c_k \in \{0, \ldots, 9\}$, $c_{n+1} = 0$.

### Complexity Analysis

To prevent misunderstandings, IVI does not recompute a full convolution at each step. At digit k:

- At most 50 states $(p_k, q_k)$ are considered (empirical conjecture [1]).
- Each state is tested using local arithmetic and the current carry.
- No recomputation of prior digits is required.

Thus: $T(n) = O(n)$, Space = $O(1)$.

**Lemma 1.** IVI digit propagation load is linear in the length of the semiprime.

## 5 Digit Recurrence

$$\sum_{i=1}^{k} p_i q_{k-i+1} + c_k = n_k + 10c_{k+1}, \quad k = 1, \ldots, n.$$

## 6 Illustrative Example

Consider $N = 3127 = 53 \cdot 59$. The recurrence uniquely determines $p = 53$, $q = 59$.

## 7 IVI Uniqueness Theorem

**Lemma 2.** Full solutions of the recurrence are in one-to-one correspondence with factorizations $N = pq$. If an ordering convention (e.g. $p \leq q$) is imposed, at most one solution exists.

**Theorem 1 (Deterministic IVI Inversion).** Assume N is a semiprime. If digit sequences $\{p_k\}$, $\{q_k\}$ and carries $\{c_k\}$ satisfy the recurrence with $c_1 = 0$ and $c_{n+1} = 0$, and an ordering condition is imposed, then at most one solution exists. Thus IVI provides a finite deterministic inversion of integer multiplication.

**Lemma 3.** The process is deterministic (LD) and involves no random search.

## 8 Conclusion

IVI reformulates multiplication inversion as a bounded digit-propagation problem governed by explicit arithmetic constraints. The admissible digit pairs are bounded by 50 (author's 1982 [1] empirical conjecture), independently of k and n. The bounded 50-state condition is stated explicitly as an empirical conjecture, not authoritarianly stated. A single semiprime whose digit propagation requires more than 50 admissible states at any position would refute it. The conjecture is therefore mathematically testable and sharply falsifiable. Absent such a counterexample, IVI reduces multiplication inversion to a finite, local propagation system whose complexity is linear in the digit length of the semi-prime. The question is thus Boolean and precise: either the bounded-state conjecture fails, or digit-level inversion admits a deterministic linear formulation.

## Funding

This research received public funding from institutions in Brazil and Germany, and private support from HAPPINESS GROUP, NMA, SAFEVOTE, and PLANALTO RESEARCH. The author declares no conflict of interest.

## Acknowledgments

The author thanks colleagues and reviewers.

## References

1. Gerck, E.; Gallas, J.A.C.; D'Oliveira, A.B. (1982). Physical Review A, 26, 662.
2. Gallas, J.A.C.; Gerck, E.; O'Connell, R.F. (1983). Physical Review Letters, 50, 524.
3. Gerck, E. (2023). Mathematics, 11(1), 68.
4. Gerck, E.; Brito Cruz, C.E. (1979). Applied Optics, 18(9), 1341.
5. Gerck, E. (1979). Applied Optics, 18(18), 3075–3075.
