import { Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  useAnswer,
  useFlashcards,
  useGenerate,
  useQuiz,
  useReview,
  type Flashcard,
  type QuizQuestion,
  type Rating,
} from "./study";

const RATINGS: { rating: Rating; label: string }[] = [
  { rating: "again", label: "Again" },
  { rating: "hard", label: "Hard" },
  { rating: "good", label: "Good" },
  { rating: "easy", label: "Easy" },
];

function CardReview({ documentId, card }: { documentId: string; card: Flashcard }) {
  const [shown, setShown] = useState(false);
  const review = useReview(documentId);
  return (
    <div className="border border-neutral-300 p-4">
      <p className="font-medium">{card.front}</p>
      {!shown ? (
        <button type="button" className="mt-3 underline" onClick={() => setShown(true)}>
          Show answer
        </button>
      ) : (
        <>
          <p className="mt-3">{card.back}</p>
          <div className="mt-3 flex gap-3">
            {RATINGS.map((r) => (
              <button
                key={r.rating}
                type="button"
                className="underline disabled:opacity-50"
                disabled={review.isPending}
                onClick={() => review.mutate({ cardId: card.id, rating: r.rating })}
              >
                {r.label}
              </button>
            ))}
          </div>
        </>
      )}
      {review.isError && (
        <p role="alert" className="text-red-700">
          {review.error.message}
        </p>
      )}
    </div>
  );
}

function QuizItem({ documentId, q }: { documentId: string; q: QuizQuestion }) {
  const answer = useAnswer(documentId);
  const [picked, setPicked] = useState<number | null>(null);
  const res = answer.data;
  return (
    <li className="border border-neutral-300 p-4">
      <p className="font-medium">{q.question}</p>
      <ul className="mt-2 space-y-1">
        {q.choices.map((c, i) => (
          <li key={c}>
            <button
              type="button"
              className={`underline ${res && i === res.answer_index ? "font-bold" : ""}`}
              disabled={answer.isPending || res !== undefined}
              onClick={() => {
                setPicked(i);
                answer.mutate({ questionId: q.id, choice: i });
              }}
            >
              {c}
            </button>
          </li>
        ))}
      </ul>
      {res && (
        <p role="status" className="mt-2 text-sm">
          {res.correct ? "Correct." : `Not quite (you chose “${q.choices[picked ?? 0]}”).`}{" "}
          {res.explanation}
        </p>
      )}
      {answer.isError && (
        <p role="alert" className="text-red-700">
          {answer.error.message}
        </p>
      )}
    </li>
  );
}

export function Study({ documentId }: { documentId: string }) {
  const cards = useFlashcards(documentId, true);
  const quiz = useQuiz(documentId);
  const gen = useGenerate(documentId);
  const first = cards.data?.[0];
  return (
    <article>
      <p className="mb-4">
        <Link to="/documents/$documentId" params={{ documentId }} className="underline">
          ← Back to book
        </Link>
      </p>
      <h2 className="text-xl font-semibold">Study</h2>
      <p className="mb-4 text-sm text-neutral-600">
        Made only from what you have already read, so nothing here spoils what comes next.
      </p>
      <div className="mb-6 flex gap-4">
        <button
          type="button"
          className="underline disabled:opacity-50"
          disabled={gen.isPending}
          onClick={() => gen.mutate("flashcards")}
        >
          Make flashcards
        </button>
        <button
          type="button"
          className="underline disabled:opacity-50"
          disabled={gen.isPending}
          onClick={() => gen.mutate("quiz")}
        >
          Make a quiz
        </button>
      </div>
      {gen.isPending && <p role="status">Generating…</p>}
      {gen.isError && (
        <p role="alert" className="text-red-700">
          {gen.error.message}
        </p>
      )}
      {gen.data && (
        <p role="status" className="mb-4 text-sm">
          Added {gen.data.created} {gen.data.kind === "quiz" ? "questions" : "flashcards"}
          {gen.data.skipped > 0 ? ` (${gen.data.skipped} skipped)` : ""}.
        </p>
      )}

      <section aria-labelledby="cards-h" className="mb-8">
        <h3 id="cards-h" className="mb-2 font-semibold">
          Flashcards due
        </h3>
        {cards.isPending && <p role="status">Loading…</p>}
        {cards.isError && <p role="alert">{cards.error.message}</p>}
        {cards.data && cards.data.length === 0 && <p role="status">Nothing due right now.</p>}
        {first && <CardReview key={first.id} documentId={documentId} card={first} />}
        {cards.data && cards.data.length > 1 && (
          <p className="mt-2 text-sm text-neutral-600">{cards.data.length - 1} more after this.</p>
        )}
      </section>

      <section aria-labelledby="quiz-h">
        <h3 id="quiz-h" className="mb-2 font-semibold">
          Quiz
        </h3>
        {quiz.isPending && <p role="status">Loading…</p>}
        {quiz.isError && <p role="alert">{quiz.error.message}</p>}
        {quiz.data && quiz.data.length === 0 && <p role="status">No questions yet.</p>}
        <ul className="space-y-3">
          {quiz.data?.map((q) => (
            <QuizItem key={q.id} documentId={documentId} q={q} />
          ))}
        </ul>
      </section>
    </article>
  );
}
