export default function Toggle({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <span className={"switch" + (checked ? " on" : "")}
            onClick={() => onChange(!checked)}
            role="switch" aria-checked={checked} tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onChange(!checked); } }}>
        <span className="knob" />
      </span>
    </label>
  );
}
