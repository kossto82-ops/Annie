# JARVIS — REFLECTION AND LEARNING

Quiero implementar un mecanismo de reflexión posterior a interacciones importantes.

## Objetivo

Después de una interacción relevante, Jarvis debería evaluar:
- What happened?
- What did I believe?
- What evidence appeared?
- What did I learn?
- Was I wrong?
- Should memory change?
- Should a belief change?
- Should future behavior change?

## Importante

Reflection NO significa simplemente pedir al LLM:
"Reflect on your answer."

Debe tener consecuencias concretas cuando corresponda:

Interaction → Evaluation → Evidence → Memory update → Belief update → Possible behavior adjustment

## Evitar

No crear:
- recuerdos infinitos
- reflexiones inútiles
- loops recursivos
- coste innecesario de tokens
- cambios automáticos peligrosos

Reflection debe ejecutarse cuando aporte valor.

## Tests

Demuestra:
1. interacción correcta
2. error de Jarvis
3. nueva evidencia
4. contradicción
5. actualización de belief
6. no-update cuando no existe evidencia suficiente

Implementa incrementalmente.
