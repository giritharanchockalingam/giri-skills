// Fictional fixture (ui-component-quality evals): a card whose props grew one by one.
interface OrderCardProps {
  id: string;
  number: string;
  customer: string;
  total: number;
  currency: string;
  paid: boolean;
  dueDate: string;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  compact?: boolean;
}

export function OrderCard(props: OrderCardProps) {
  return (
    <div className="card md:w-[720px]">
      <span>{props.number}</span>
      <span>{props.customer}</span>
      <span>{props.paid ? "Paid" : `Due ${props.dueDate}`}</span>
    </div>
  );
}
