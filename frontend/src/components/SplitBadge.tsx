import type { Translate } from "../i18n/translations";
import { dataSplitFor, splitPeriodsFor } from "../lib/dataSplit";

type SplitBadgeProps = {
  t: Translate;
  targetDate: string;
  modelVersion?: string | null;
};

const LABELS = {
  train: { label: "splitTrain", title: "splitTrainTitle" },
  validation: { label: "splitValidation", title: "splitValidationTitle" },
  test: { label: "splitTest", title: "splitTestTitle" },
} as const;

export function SplitBadge({ t, targetDate, modelVersion }: SplitBadgeProps) {
  const split = dataSplitFor(targetDate, modelVersion);
  const periods = splitPeriodsFor(modelVersion);
  const range = {
    train: { from: periods.trainStart, to: periods.trainEnd },
    validation: { from: periods.trainEnd + 1, to: periods.validationEnd ?? periods.trainEnd },
    test: { from: periods.testStart, to: periods.testEnd },
  }[split];
  const title = t(LABELS[split].title, { from: String(range.from), to: String(range.to) });
  return (
    <span className={`tag row-badge split-badge split-${split}`} title={title}>
      {t(LABELS[split].label)}
    </span>
  );
}
