<?php
        include_once 'apicrm.php';

        $api = new ApiCrm();

        $resultado = $api->getAll();

        header("Content-Type: application/json;charset=utf-8");

        echo json_encode(array($resultado));
?>
