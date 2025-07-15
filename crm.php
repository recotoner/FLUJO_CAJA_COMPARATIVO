<?php
        include_once 'db.php';

        class Crm extends DB{
        

                function obtenerDatos(){
                        $query = $this->connect()->query("SELECT * from cluster_retail");
                        return $query;
                }
        }
?>
