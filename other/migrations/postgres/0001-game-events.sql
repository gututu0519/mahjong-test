CREATE FUNCTION emit_decision_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  INSERT INTO merchant_round_events(merchant_id,game_id,round_id,decision_id,created_at)
  VALUES(NEW.merchant_id,NEW.game_id,NEW.id,NEW.id,extract(epoch FROM clock_timestamp())::bigint);
  RETURN NEW;
END $$;
CREATE TRIGGER round_event_decision_insert AFTER INSERT ON prebet_rounds FOR EACH ROW EXECUTE FUNCTION emit_decision_event();
CREATE TRIGGER round_event_decision_update AFTER UPDATE OF policy_json,plan_json,error_code ON prebet_rounds FOR EACH ROW EXECUTE FUNCTION emit_decision_event();
CREATE FUNCTION emit_operation_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  INSERT INTO merchant_round_events(merchant_id,game_id,round_id,decision_id,created_at)
  VALUES(NEW.merchant_id,NEW.game_id,NEW.candidate_json::jsonb #>> '{event,round_id}',NEW.candidate_json::jsonb ->> 'decision_id',extract(epoch FROM clock_timestamp())::bigint);
  RETURN NEW;
END $$;
CREATE TRIGGER round_event_operation_insert AFTER INSERT ON game_operations FOR EACH ROW EXECUTE FUNCTION emit_operation_event();
CREATE TRIGGER round_event_operation_update AFTER UPDATE OF status,debit_json,response_json,error_code ON game_operations FOR EACH ROW EXECUTE FUNCTION emit_operation_event();
