import { Toast } from "@base-ui/react/toast";
import { CircleCheck, X } from "lucide-react";
import { Link } from "react-router-dom";
import styles from "./toast.module.css";

export const toast = Toast.createToastManager<{ href?: string }>();

export function Toaster() {
  return <Toast.Provider toastManager={toast} timeout={6000} limit={3}>
    <Toast.Portal><Toast.Viewport className={styles.viewport} aria-label="Notifications"><ToastList /></Toast.Viewport></Toast.Portal>
  </Toast.Provider>;
}

function ToastList() {
  const { toasts } = Toast.useToastManager<{ href?: string }>();
  return toasts.map(item => <Toast.Root key={item.id} toast={item} className={styles.toast} swipeDirection="right" data-testid="training-toast">
    <Toast.Content className={styles.content} aria-hidden={false}>
      <CircleCheck size={20} className={styles.icon} aria-hidden="true" />
      <div className={styles.text}>
        <Toast.Title className={styles.title} />
        <Toast.Description className={styles.description} />
        {item.data?.href && <Toast.Action className={styles.action} aria-hidden={false} nativeButton={false} render={<Link to={item.data.href} />} onClick={() => toast.close(item.id)}>View results</Toast.Action>}
      </div>
      <Toast.Close className={styles.close} aria-hidden={false} aria-label="Dismiss notification"><X size={16} aria-hidden="true" /></Toast.Close>
    </Toast.Content>
  </Toast.Root>);
}
